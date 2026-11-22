# Arquitectura del MVP

## Vista general

Un único frontend React sirve dos experiencias distintas — la del
estudiante (pública, sin login) y la del docente (protegida con JWT) — tal
como pide cap. 15: *"La captura se realizará en el navegador mediante APIs
y eventos nativos de la plataforma web"* y *"el código cliente captura las
señales habilitadas y envía lotes de eventos a la API"*. No hay una
extensión de navegador ni ningún componente instalable aparte (ver
`docs/bitacora.md`, Incremento 2b, para la corrección de arquitectura que
llevó a este diseño).

```
┌───────────────────────────────────────────┐
│         Frontend React (dashboard/)        │
│                                             │
│  /exam/:joinCode        /login, /exams,... │
│  (estudiante,           (docente, JWT)     │
│   sin login)                               │
│  ┌───────────────┐     ┌─────────────────┐ │
│  │ TakeExam.tsx  │     │ ExamsList.tsx   │ │
│  │ + capture.ts  │     │ SessionsList.tsx│ │
│  │ + syncQueue.ts│     │ SessionDetail   │ │
│  │ (misma pestaña)│    │ PendingValid.   │ │
│  └───────┬───────┘     └────────┬────────┘ │
└──────────┼──────────────────────┼──────────┘
           │ HTTPS (JSON, lotes)  │ HTTPS (JSON), JWT
           ▼                      ▼
┌─────────────────────────────────────────────┐
│              Backend (FastAPI)               │
│  • Auth (JWT docente)                        │
│  • Sesiones / eventos (session_token opaco)  │
│  • Procesamiento determinístico + IF         │
│  • Indicadores + Revisión docente            │
└────────────────────┬──────────────────────────┘
                      ▼
           ┌────────────────────┐
           │ PostgreSQL (prod)  │
           │ SQLite (dev local) │
           └────────────────────┘
```

Los diagramas formales para el documento (componentes, flujo de información
en forma de secuencia y clases del dominio) están en TikZ en
`latex/figures/diagramas/` (T25) y se compilan con la tesis.

Monolito modular (cap. 15): un solo backend FastAPI concentra sesiones,
eventos, procesamiento e indicadores. No hay microservicios ni colas de
mensajería — no se justifican en este alcance. La API de sesiones no sabe
ni le importa qué tipo de cliente le habla (eso quedó demostrado al migrar
de la extensión a `TakeExam.tsx` sin tocar el backend).

**Limitación consciente de este diseño:** al capturar solo dentro de la
propia pestaña de ImprontIA (y no mediante inyección en cualquier sitio,
como hacía la extensión), la plataforma necesita alojar ella misma la
superficie donde el estudiante escribe su respuesta — de ahí el campo
`Exam.prompt_text` y el textarea de `TakeExam.tsx`. Si el examen real vive
en otra plataforma (Moodle, Forms), el mecanismo de asociación queda
abierto, tal como cap. 13 ya lo señala explícitamente.

## Modelo de datos

Sigue de cerca el ER de cap. 15 ("Modelo de datos"), rediseñado en el
Incremento 5 (ver bitácora) a partir del más simple del Incremento 1:

```
User (docente) ──< Exam ──< PolicyCapture (versionada, inmutable)
                    │              │
                    └──< Session ──┘   (fija policy_id al iniciar; RNF04)
                          │
                          ├──< Event    (fila por evento, seq monotónico, item_ref opcional)
                          ├──< Metric   (determinística; item_ref opcional para desglose por ítem)
                          ├──< Indicator ──< IndicatorMetric >── Metric   (N:M, RNF05)
                          └──< Review   ──< ReviewIndicator  >── Indicator (N:M, RF11)
```

- **Exam**: identidad estable (`name`, `join_code`, `prompt_text` — la
  consigna, revelada recién tras iniciar sesión). Ya no tiene `info_text`/
  `rules_text`/`allowed_signals` directos. La API expone además
  `policy_version` (cantidad de versiones de política; 1 = la original).
- **PolicyCapture**: snapshot versionado de qué se informa (RF01/RF02) y
  qué señales se habilitan (RF04). Inmutable — editar la política de un
  examen crea una fila nueva (`POST /exams/{id}/policy`, con UI en
  `PolicyCard.tsx` desde el Incremento 8), nunca actualiza la existente,
  para que un cambio posterior no reinterprete sesiones ya rendidas bajo
  una versión anterior (RNF04).
- **Session**: fija `policy_id` al momento de `POST /sessions/start` y lo
  conserva para siempre, aunque la política "vigente" del examen cambie
  después.
- **Event**: una fila por evento (no un blob JSON por lote), indexada por
  `(session_id, seq)`. `item_ref` opcional asocia el evento a una
  pregunta/ítem, sin que ImprontIA administre el contenido de las
  preguntas en sí. Los eventos de teclado guardan solo el instante de cada
  pulsación, **no qué tecla** (Incremento 9). Además de las interacciones,
  el cliente puede enviar dos eventos de **estado de la captura**
  (`buffer_overflow`, `sync_failure`; Incremento 10).
- **Metric**: determinística (`processing/features.py`), con `item_ref`
  opcional para desglose por ítem además del agregado de sesión completa.
- **Indicator**: umbral determinístico (`processing/indicators.py`) o
  atipicidad frente a la línea base poblacional (`processing/anomaly.py`).
  Tiene `level` (low/medium/high) para priorizar revisión (RNF08), y se
  linkea a las métricas reales que lo originaron vía `IndicatorMetric`
  (relación N:M, no solo el JSON `explanation`). El indicador
  `captura_incompleta` es **informativo**: se muestra pero no marca la
  sesión como "requiere revisión" (Incremento 10).
- **Review**: única fuente de decisión académica (RF10), siempre creada
  por un docente, solo inserción. Puede apuntar a indicadores puntuales vía
  `ReviewIndicator` (N:M) — o a ninguno, para una revisión "sin
  observaciones". El **estado de revisión** de una sesión (`sin_revision` /
  `revisada` / `validacion_pendiente`) no se guarda: se deriva de la última
  `Review` (Incremento 8), así que cerrar un pedido de validación adicional
  agrega una revisión nueva en vez de editar la anterior.

## Captura y sincronización (cliente)

- `capture.ts` registra listeners nativos del DOM y descarta en el acto los
  eventos de categorías no habilitadas (RF04). Del portapapeles solo toma la
  longitud de lo pegado, y solo si la categoría está habilitada.
- `syncQueue.ts` (Incremento 10, lógica pura con pruebas en
  `dashboard/tests/`) acumula los eventos en un **buffer local acotado**
  (20 000 eventos) y los envía en lotes numerados (el backend descarta un
  lote reenviado con el mismo número). Sin fallas, un envío cada 5 s; ante
  fallas, **backoff exponencial** (×2 por falla, ±20 % aleatorio, tope
  60 s), con reintento inmediato si el navegador avisa `online`. Si el
  buffer se llena, se cuentan los descartados y se envía un
  `buffer_overflow`; si hubo 3 o más fallas seguidas, al recuperar se envía
  un `sync_failure`. Verificado de punta a punta con `scripts/prueba_red.py`.

## Procesamiento e inteligencia artificial

Tres niveles, tal como distingue cap. 15 (`processing/`):

1. **Determinístico** (`features.py`): estadísticas puras sobre los eventos
   de una sesión — sin ninguna librería de ML. Incluye dos métricas de
   integridad de la captura (`capture_dropped_events`, `sync_failure_count`).
2. **Indicadores por umbral** (`indicators.py`): reglas explícitas sobre
   eventos discretos/contables (paste, cambios de pestaña, pérdida de
   foco) — "marcas binarias", en términos de cap. 15 — más el aviso
   informativo de captura incompleta.
3. **Isolation Forest sobre línea base poblacional** (`anomaly.py`): las
   métricas *continuas* (tiempos de tecla, velocidad de mouse) de la
   sesión se comparan contra las de otras sesiones ya finalizadas **de la
   misma evaluación** — nunca contra el historial del propio estudiante.
   Requiere `MIN_SESSIONS_FOR_MODEL = 20` sesiones previas para activarse;
   por debajo de eso, sklearn literalmente no logra aislar ni un outlier
   extremo (hallazgo empírico documentado en el propio módulo y en la
   bitácora, Incremento 5) — no hay indicador de IA hasta entonces, lo cual
   es el estado esperado hasta contar con datos de sesiones piloto reales.
   El **nivel** del indicador se fija por **percentiles** sobre la
   distribución de scores de esa misma línea base (alto = dentro del 5 % más
   atípico; Incremento 10), y al docente se le muestra esa posición relativa
   y los factores más desviados, nunca el score crudo.

`pipeline.py::evaluate_session` combina los niveles 2 y 3 para una sesión
(métricas → indicadores) sin tocar la base de datos. La usan tanto el
endpoint `POST /sessions/{id}/end` como la evaluación reproducible, de modo
que lo que se mide es exactamente el código que corre en la API.

## Evaluación reproducible (Incremento 6)

`app/evaluation/` + `scripts/evaluar.py`: generador de sesiones sintéticas
(eventos en el mismo formato que `capture.ts`, perfiles normal y cuatro
anómalos), protocolo de repeticiones con semillas fijas y métricas FAR
(anomalías no detectadas), FRR (falsas alarmas), AUC-ROC, AP y EER. Valida
el **procedimiento**, no el desempeño real (que depende del piloto). El
reporte generado vive en `docs/evaluacion/resultados_sinteticos.md`.

## Pruebas end-to-end (Incrementos 9 y 10)

- `scripts/prueba_interna.py`: levanta backend + dashboard reales y, con
  Playwright/Chromium, rinde sesiones guionadas desde la vista del
  estudiante (normal, pegado masivo, cambios de foco, transcripción a ritmo
  constante). Verifica indicadores en la API, que la vista docente muestre
  lo mismo y que ningún evento persistido contenga texto ni identifique la
  tecla pulsada. Resultados e interpretación en
  `docs/evaluacion/prueba_interna.md`; repetición manual en
  `docs/evaluacion/protocolo_prueba_manual.md`.
- `scripts/prueba_red.py`: corte prolongado de red, buffer lleno y
  reconexión avisada por el navegador. Verifica el backoff, que no se pierda
  ninguna pulsación sin registro y que el docente vea el aviso de captura
  incompleta. Resultados en `docs/evaluacion/prueba_red.md`.

## Trazabilidad a los requerimientos (cap. 13)

| Requisito | Dónde vive |
|---|---|
| RF01/RF02 — Info previa y reglas | `GET /exams/{join_code}/info` (público, sin login, lee `Exam.current_policy`) + `TakeExam.tsx`, mostrado antes del checkbox de consentimiento: texto del docente + lista de señales habilitadas con su descripción precisa (`format.ts::SIGNAL_STUDENT_DESCRIPTIONS`). La consigna, en cambio, se oculta hasta después |
| RF03/RF04 — Registro acotado a señales habilitadas | `PolicyCapture.allowed_signals` + filtro en `capture.ts::isAllowed` (descarta antes de guardar en el buffer local, no solo antes de enviar; una política sin señales no captura nada); edición versionada en `PolicyCard.tsx` |
| RF05 — Contexto de la evaluación | `Session.context` (JSON libre: curso, actividad, etc.) |
| RF06/RF07 — Identificar sesiones para revisión | `Session.needs_review` (calculado al finalizar; solo cuentan los indicadores que priorizan) + filtro en `SessionsList.tsx`, que además muestra el estado de la revisión docente |
| RF08/RF09 — Evidencia contextualizada + trazabilidad | `SessionDetail.tsx`: contexto + métricas + indicadores; cada indicador linkeado a sus `Metric` reales vía `IndicatorMetric` |
| RF10 — Indicador ≠ decisión académica | Ningún endpoint marca una sesión como "fraude"; el texto de la UI lo aclara explícitamente; `Indicator` no tiene columna de veredicto; la única fuente de decisión es `Review` |
| RF11 — Validación adicional | `POST /sessions/{id}/reviews` con `action=additional_validation` (opcionalmente ligada a indicadores vía `ReviewIndicator`); `GET /sessions?review_status=validacion_pendiente` + vista `/validaciones` (`PendingValidations.tsx`) con los casos abiertos de todas las evaluaciones; historial de revisiones en `SessionDetail.tsx`. ImprontIA indica la validación pero no la ejecuta (cap. 13) |
| RNF01 — Minimización de datos | Filtro de `allowed_signals` (lista vacía = no se captura nada); `capture.ts` nunca lee el valor del textarea, del portapapeles solo toma la longitud (y solo si la categoría está habilitada), y de cada pulsación solo el instante (sin `key` ni `code`); el participante se identifica con un código seudónimo. Verificado sobre la base real en la prueba interna |
| RNF02 — Transparencia | Info mostrada = info efectivamente usada para habilitar señales (misma fila `PolicyCapture`); la lista de señales que ve el estudiante se genera de la misma `allowed_signals` que limita la captura |
| RNF03 — Confidencialidad | JWT por docente, cada query de sesiones filtra por `teacher_id`; `session_token` opaco por sesión |
| RNF04 — Integridad de registros | `Event` y `Review`, solo inserción; `PolicyCapture` inmutable — una sesión conserva la versión que aceptó aunque el examen cambie después; recepción idempotente por número de lote; buffer local acotado con registro de descartes y de fallas persistentes (`buffer_overflow`, `sync_failure` → indicador informativo `captura_incompleta`) |
| RNF05/RNF06 — Trazabilidad y explicabilidad | `IndicatorMetric` (N:M real, no solo JSON) para reglas por umbral; para el indicador de IA, posición relativa en la línea base (percentil) y z-score de las métricas más desviadas (`anomaly.py`), sin exponer el score crudo |
| RNF07 — Baja interferencia | Captura asíncrona vía listeners nativos del DOM, envío por lotes cada 5 s con backoff ante fallas (`syncQueue.ts`); el estudiante puede seguir escribiendo sin conexión |
| RNF08 — Usabilidad docente | Filtro "solo requieren revisión", `Indicator.level` para priorizar, nombres legibles de indicadores, indicadores resumidos antes de las métricas crudas, contador de validaciones pendientes en la barra superior, avisos informativos diferenciados |
| RNF09 — Escalabilidad | Abierto — sin probar bajo carga (el filtro por estado de revisión se resuelve en memoria; ver bitácora, Incremento 8) |
| RNF10 — Retención limitada | Abierto — no implementado todavía (ver bitácora) |

## Decisiones técnicas y su porqué

Ver `docs/bitacora.md` para el detalle increment-by-increment. Resumen:

- **SQLite en dev, PostgreSQL en `docker-compose.yml`**: sin Docker
  disponible en esta máquina, se priorizó tener algo funcionando hoy. El
  código no depende del motor (SQLAlchemy + `JSONB.with_variant(JSON, sqlite)`).
- **Isolation Forest sobre línea base poblacional, no per-student**: la
  tesis (cap. 15) rechaza explícitamente comparar contra el historial
  propio del estudiante (el MVP no puede garantizar ese historial, y
  además tomaría el patrón habitual de cada quien como su propia
  referencia). `processing/features.py` (puro), `indicators.py` (umbrales)
  y `anomaly.py` (Isolation Forest) están separados en tres módulos con
  responsabilidades distintas, tal como distingue cap. 15 en tres niveles
  conceptuales.
- **Nivel del indicador de IA por percentiles** (Incremento 10): relativo a
  la línea base de cada evaluación, no a la escala del score, que cambia
  con la población.
- **Sin cuentas de estudiante**: un `session_token` por sesión es
  suficiente para lo que pide RNF03 en este alcance y evita construir un
  sistema de autenticación de estudiantes que la tesis no pide todavía.
- **Captura embebida en la plataforma, no extensión de navegador**: la
  primera versión de este MVP construyó una extensión de Chrome completa
  (manifest, content script, service worker) basada en un documento de
  planificación más viejo que cap. 15, sin cruzarlo contra el texto vigente
  de la tesis. Cap. 15 pide explícitamente que la captura sea "código
  cliente" de "la plataforma web" — se corrigió retirando la extensión y
  moviendo la misma lógica de captura a una vista del propio frontend
  (`TakeExam.tsx` + `capture.ts`). Ver `docs/bitacora.md`, Incremento 2b.
- **Pulsaciones sin identificar la tecla** (Incremento 9): el backend
  empareja keydown/keyup en orden de llegada; es exacto mientras las teclas
  se suelten en el orden en que se presionaron, y evita guardar una
  secuencia de teclas de la que se podría reconstruir el texto.
- **Una mala conexión no prioriza la revisión** (Incremento 10): la captura
  incompleta se informa al docente como aviso, sin marcar la sesión.
- **Timestamps en UTC explícito**: la base guarda `datetime.utcnow()`
  (naive); la API los serializa siempre con `+00:00` (`schemas.datetime_utc`)
  y el dashboard los muestra en hora local con `format.ts::formatDateTime`.
