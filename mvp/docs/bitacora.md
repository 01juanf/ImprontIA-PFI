# Bitácora de construcción del MVP

Registro incremental de qué se construyó, en qué orden, por qué, y qué quedó
pendiente. Cada incremento es funcional por sí mismo y fue probado antes de
pasar al siguiente (metodología ágil: nada se documenta como "hecho" sin
haberse corrido).

Referencias constantes: capítulo 13 (Requerimientos, RF/RNF) y capítulo 15
(Tecnologías) de la tesis (`../../chapters/`).

---

## Punto de partida

Antes de escribir código se revisó lo que ya existía en el proyecto:

- `chapters/chapter13_requerimientos.tex`: 8 Historias de Usuario, 11 RF, 10 RNF.
- `chapters/chapter15_tecnologias.tex`: stack ya decidido y defendido —
  monolito modular, React+TypeScript, FastAPI, PostgreSQL, **procesamiento
  determinístico sin ML en el alcance del MVP** (el ML es explícitamente
  "no forma parte del alcance funcional del MVP").
- `extension-mvp/`: un prototipo de extensión de Chrome ya funcional, que
  captura señales (teclado, mouse, scroll, visibilidad, portapapeles) de
  forma privacy-safe (nunca guarda texto, solo metadatos) pero **sin
  backend**: todo quedaba en `chrome.storage.local` y se exportaba a mano.
- `ImprontIA_Technical_Plan.md` (carpeta raíz de `TESIS/`, no es parte de la
  tesis): un documento de planificación más antiguo (junio) que sí proponía
  explícitamente una extensión de Chrome como mecanismo de despliegue.

Decisión inicial (**luego corregida, ver Incremento 2b**): se tomó
`extension-mvp/` como base y se le agregó conexión a un backend real, sin
cruzar antes ese criterio contra el capítulo 15 ya redactado. Fue un error:
el capítulo 15 (el documento vigente, no el plan de junio) nunca pide una
extensión — pide que la captura ocurra "en el navegador mediante APIs y
eventos nativos de la **plataforma web**", es decir, como parte del propio
frontend de ImprontIA. El error se detectó por una pregunta directa del
usuario y se corrigió en el Incremento 2b.

---

## Incremento 1 — Backend: modelo de datos y API de sesiones

**Objetivo:** poder crear una evaluación, iniciar una sesión, mandar eventos,
cerrarla, y consultar el resultado — sin extensión ni frontend todavía,
probado con `curl`.

**Qué se construyó** (`mvp/backend/`):
- Modelo de datos (`app/models.py`) que traduce las entidades que cap. 15
  deja pendientes de diagramar: `User` (docente), `Exam` (evaluación),
  `Session` (sesión), `EventBatch` (evento, en lotes), `Metric` (métrica),
  `Indicator` (indicador) y `Review` (revisión). Cada tabla está comentada
  con el RF/RNF que la origina.
- Autenticación JWT para docentes (`app/auth.py`). El estudiante **no tiene
  cuenta**: su credencial es un `session_token` opaco, válido solo para esa
  sesión puntual — más simple que un sistema de cuentas y suficiente para
  lo que pide RNF03 (nadie más puede escribir eventos en esa sesión).
- Endpoints (`app/routers/`): `POST /auth/login`, `POST /exams`,
  `GET /exams`, `POST /sessions/start`, `POST /sessions/{id}/events`,
  `POST /sessions/{id}/end`, `GET /sessions`, `GET /sessions/{id}`,
  `POST /sessions/{id}/reviews`.

**Desviación documentada del stack:** cap. 15 fija PostgreSQL como único
motor. Esta máquina no tiene Docker instalado, así que para poder levantar
algo real hoy mismo, `DATABASE_URL` cae por defecto a SQLite
(`app/database.py`). El código no cambia para usar Postgres — es una
variable de entorno — y las columnas JSON usan
`JSONB().with_variant(JSON(), "sqlite")` para que el mismo modelo sirva en
ambos motores. `docker-compose.yml` ya está armado con Postgres real para
cuando haya Docker disponible.

**Prueba:** flujo completo con `curl` (login → crear examen → iniciar sesión
→ mandar eventos con un `paste` de 500 caracteres → finalizar → consultar
detalle) devolvió 2 indicadores generados correctamente. Se agregaron 15
tests automáticos (`tests/`): 5 unitarios de extracción de features, 4 de
generación de indicadores, 6 de integración de la API (incluyendo que un
docente no pueda ver sesiones de otro docente). `pytest` → 15 passed.

---

## Incremento 2 — Conectar la extensión de Chrome al backend

**Objetivo:** que `extension-mvp/` deje de ser un prototipo aislado y hable
con el backend real, sin perder ninguna de sus garantías de privacidad.

**Qué se hizo** (`mvp/extension/`, copiada y adaptada desde `extension-mvp/`):
- `content.js` **no se tocó**: ya estaba bien diseñado (nunca captura texto
  ni contenido de portapapeles) y no necesita saber nada del backend.
- `background.js`: se agregó el llamado real a
  `POST /sessions/start` / `/events` / `/end`, una cola de lotes pendientes
  (`pending_batches`) y un `chrome.alarms` cada ~15s que reintenta el envío
  si falla (backoff simplificado a intervalo fijo, no exponencial — ver
  limitaciones en `mvp/extension/README.md`). El `chrome.storage.local`
  sigue existiendo igual que antes: es el respaldo local que permite
  exportar el JSON manualmente pase lo que pase con el backend.
- Nuevo endpoint público `GET /exams/{join_code}/info` (sin login) para que
  el popup pueda mostrar al estudiante qué se registra y qué reglas aplican
  **antes** de que consienta (RF01/RF02) — el flujo anterior no contemplaba
  esto porque no existía backend contra el cual consultarlo.
- RF04 ("limitar el registro a las señales informadas"): se agregó un
  filtro en `background.js` que descarta, antes de guardar en cualquier
  lado (local o backend), los eventos cuya categoría no esté en
  `allowed_signals` del examen.
- El popup ahora pide un "Código de examen" (`join_code`, ej. `A3F9C1`)
  en vez de un "ID de actividad" de texto libre, y agrega un botón
  **Verificar** que trae y muestra la info/reglas del examen.

**Bug real encontrado y corregido:** los eventos que se encolaban para el
backend llevaban `ts` (timestamp absoluto de `Date.now()`), pero el backend
espera `t` (milisegundos relativos al inicio de sesión, el mismo formato
que ya usaba el export local). Sin la conversión, el procesamiento fallaba
con `KeyError: 't'` al finalizar la sesión. Se corrigió convirtiendo en
`appendEvents` antes de encolar.

**Cómo se probó (sin poder cargar la extensión en un Chrome real):** se
escribió un harness en Node (`vm` + mocks de `chrome.storage`/`chrome.alarms`/
`chrome.runtime`) que ejecuta el `background.js` **real**, sin modificarlo,
contra el backend corriendo de verdad. El harness fue el que encontró el bug
de `ts`/`t` de arriba. Con la corrección, los 15 checks del flujo completo
pasan: verificar examen → iniciar sesión → mandar eventos mezclando
categorías permitidas y no permitidas → confirmar que el filtro RF04
funcionó → forzar el flush → finalizar → verificar del lado docente que el
backend recibió justo los eventos filtrados y generó el indicador esperado
→ exportar y confirmar que la privacidad del JSON se mantiene intacta.

**Este incremento quedó obsoleto y su código se retiró — ver Incremento 2b.**

---

## Incremento 2b — Corrección: captura embebida en la plataforma, no extensión

**Qué pasó:** el usuario preguntó "¿por qué una extensión de Chrome? ¿Lo
dice el documento?" — la respuesta, al releer cap. 13 y 15 con esa pregunta
puntual, fue no. El capítulo 15 dice explícitamente:

> "La captura se realizará en el navegador mediante APIs y eventos nativos
> de la plataforma web" (línea 55).
>
> "El navegador obtiene y ejecuta el frontend web; durante la sesión del
> estudiante, **el código cliente** captura las señales habilitadas y envía
> lotes de eventos a la API" (línea 81).

Ninguno de los dos capítulos formales de la tesis menciona una extensión.
Esa idea venía únicamente de `ImprontIA_Technical_Plan.md`, un documento de
planificación de junio, más viejo que los capítulos 13/15 (agosto) y
aparentemente superado por ellos. El error fue no cruzar ese supuesto contra
el documento vigente antes de construir todo el Incremento 2 sobre él.

**Qué cambió:**
- Se eliminó `mvp/extension/` (no se tocó `extension-mvp/` en la raíz de
  `TESIS/`, que es un artefacto del usuario, previo a este MVP).
- Se agregó `Exam.prompt_text` (la consigna del examen): dado que ahora la
  plataforma aloja la superficie de respuesta, necesita algo que mostrar.
  Se decidió que **no** se revela en `GET /exams/{join_code}/info` (RF01/02,
  antes del consentimiento) sino recién en la respuesta de
  `POST /sessions/start` — evita que cualquiera con el código vea la
  consigna sin haber iniciado una sesión real.
- Se agregó una vista pública nueva en el dashboard React,
  `/exam/:joinCode` (`TakeExam.tsx`), sin autenticación (el estudiante sigue
  sin tener cuenta): verificación del código → info/reglas → consentimiento
  → consigna + textarea de respuesta → captura de eventos en la misma
  página → sincronización con el backend → finalizar.
- Se escribió `capture.ts`: la misma lógica de `content.js` (qué eventos
  escuchar, qué categorías de señal filtrar por RF04, nunca leer el valor
  del textarea) pero como módulo de la propia página en vez de contenido
  inyectado por una extensión. El backend no necesitó ningún cambio de
  diseño — la API de sesiones ya era agnóstica al tipo de cliente.
- La sincronización usa `fetch(..., { keepalive: true })` en el intento
  final (`beforeunload`), que es el equivalente moderno y con headers
  personalizables de lo que en la extensión resolvía `chrome.alarms`.

**Ventajas no buscadas de la corrección:** no hace falta que cada estudiante
instale nada; no hace falta `host_permissions: <all_urls>` ni justificar
ese permiso ante Chrome Web Store; funciona en cualquier navegador, no solo
Chromium. Como contrapartida (documentado en `ARCHITECTURE.md`), la captura
ahora solo ve lo que pasa **dentro de la pestaña de ImprontIA** — de ahí que
la plataforma tenga que alojar la superficie de respuesta para que el
tecleo/mouse real del examen ocurra donde se lo puede observar.

**Prueba:** flujo completo en el navegador real (no un harness): crear
examen con consigna desde el dashboard → abrir `/exam/{código}` → ver
info/reglas sin la consigna → consentir → ver la consigna → escribir y
simular un `paste` de 300 caracteres → esperar el sync automático de 5s →
finalizar → volver al dashboard docente → la sesión aparece "Requiere
revisión" con el indicador `paste_volume_alto` y su métrica de origen
(`paste_chars_total = 300`, umbral 200). 16/16 tests de backend siguen en
verde (se actualizaron los que creaban exámenes, para incluir `prompt_text`,
y se agregó uno nuevo que confirma que la consigna no se filtra antes de
iniciar sesión).

---

## Incremento 3 — Procesamiento determinístico (métricas + indicadores)

Se construyó junto con el Incremento 1 (vive en
`mvp/backend/app/processing/`) porque el endpoint `POST /sessions/{id}/end`
lo dispara directamente, pero se documenta aparte porque es su propio
requisito (cap. 15, sección "Procesamiento e IA").

- `features.py`: funciones puras que calculan, a partir de la lista de
  eventos crudos de una sesión, estadísticas de teclado (dwell time, flight
  time), mouse (velocidad), atención (cambios de pestaña, tiempo de foco
  perdido) y portapapeles (cantidad de caracteres pegados) — sin ninguna
  librería de ML, tal como exige el alcance del MVP en cap. 15.
- `indicators.py`: umbrales explícitos (`THRESHOLDS`, todos placeholders
  documentados como pendientes de calibración con datos reales, igual que
  dice cap. 15) que convierten esas métricas en indicadores. Cada indicador
  guarda qué métrica y qué umbral lo originó (`explanation`), para que el
  docente pueda rastrear el origen (RF09, RNF05) sin que el sistema le
  diga "esto es fraude" (RF10, RNF06).

---

## Incremento 4 — Dashboard docente (React + TypeScript)

**Objetivo:** que un docente pueda loguearse, crear una evaluación, ver qué
sesiones requieren revisión, y consultar la evidencia con trazabilidad.

**Qué se construyó** (`mvp/dashboard/`, Vite + React 19 + TypeScript,
`react-router-dom` para las rutas — sin librerías adicionales: el alcance
del MVP no justifica React Query ni un design system todavía):
- `Login.tsx`: login JWT.
- `ExamsList.tsx`: crear evaluación (nombre, info previa, reglas, señales
  habilitadas) y ver el `join_code` para compartir con los estudiantes.
- `SessionsList.tsx`: sesiones de una evaluación, con filtro "solo las que
  requieren revisión" (RF07).
- `SessionDetail.tsx`: contexto, indicadores (con la métrica/umbral que los
  originó, y una nota explícita de que no son una conclusión de fraude),
  todas las métricas calculadas, y las dos acciones de revisión docente
  (RF11): "Marcar como revisada" / "Requiere validación adicional", con
  notas opcionales.
- `TakeExam.tsx` (agregado en el Incremento 2b, documentado ahí en detalle):
  la vista pública `/exam/:joinCode` donde el estudiante rinde, con la
  captura de señales corriendo en la misma página (`capture.ts`).

**Prueba real en navegador (primera versión, con la extensión):** login →
se ven los exámenes creados por el harness de aquel entonces → entrar a
sesiones → la sesión de prueba aparece marcada "Requiere revisión" → el
detalle muestra el indicador `paste_volume_alto` con su métrica de origen →
clic en "Marcar como revisada" → se confirmó con una consulta directa a la
base de datos que el registro de `Review` quedó persistido. Repetido
íntegramente después del Incremento 2b con la vía `/exam/:joinCode` en vez
de la extensión — mismo resultado (ver esa sección).

---

## Incremento 5 — Rediseño de esquema + Isolation Forest poblacional

**Qué pasó:** mientras se construía el MVP, el usuario editó en paralelo el
capítulo 15 (commit propio `b0f5783`, ajeno a este trabajo) y preguntó por
qué existía la extensión de Chrome. Al revisar el capítulo actualizado para
responder esa pregunta aparecieron cambios adicionales, más grandes que el
punto de la extensión: el componente de IA pasó a ser **requisito del MVP,
no postergable** (antes decía explícitamente lo contrario), y se agregó una
sección completa de "Modelo de datos" con una estructura más fina que la
implementada en el Incremento 1 (`politica_captura` versionada, `evento`
por fila con `item_ref`, relaciones N:M explícitas `indicador_metrica` y
`revision_indicador`). El usuario pidió resolver las cuatro brechas, en ese
orden: esquema → tablas N:M → Isolation Forest.

**Rediseño de esquema** (`app/models.py`, reescrito):
- `PolicyCapture` (`policy_captures`): snapshot inmutable de `info_text`,
  `rules_text`, `allowed_signals`. `Exam` ya no tiene esos campos — solo
  identidad (`name`, `join_code`, `prompt_text`). Cada `Session` fija
  `policy_id` al iniciar y lo conserva aunque el docente edite la política
  después (RNF04). Nuevo endpoint `POST /exams/{id}/policy` crea una
  versión nueva sin tocar la vigente.
- `Event` (`events`) reemplaza a `EventBatch`: una fila por evento
  (`seq` monotónico asignado por el servidor, `client_t`, `type`,
  `item_ref` opcional, `payload` JSON con el resto de los campos), no un
  blob JSON por lote. El transporte de red sigue siendo por lotes
  (`POST /sessions/{id}/events` recibe un array); lo que cambió es cómo se
  persiste del lado del servidor.
- `Metric` ahora tiene `item_ref` opcional: además del agregado de sesión
  completa (`item_ref=None`), si los eventos traen `item_ref` se calculan
  métricas también por ítem — sin crear una entidad "pregunta" propia
  (cap. 15 es explícito: ImprontIA no administra el contenido de las
  preguntas). `TakeExam.tsx` no genera `item_ref` todavía (una sola
  consigna) — la columna queda lista para cuando haya multi-ítem.
- `IndicatorMetric` y `ReviewIndicator`: tablas de unión N:M reales. Un
  indicador ahora se linkea a las filas de `Metric` que lo originaron (no
  solo a un JSON descriptivo), y una revisión puede indicar explícitamente
  a qué indicadores puntuales atiende (`ReviewCreate.indicator_ids`).
- `Indicator.level` (low/medium/high): prioriza qué revisar primero
  (RNF08), mapeado a mano por tipo de indicador en `indicators.py`.

**Isolation Forest sobre línea base poblacional** (`app/processing/anomaly.py`,
nuevo módulo):
- Solo las métricas continuas (dwell/flight time, velocidad de mouse)
  entran al modelo — los eventos discretos (paste, tab switch) siguen
  cubiertos por las reglas de `indicators.py`, tal como distingue cap. 15.
- La población de comparación son las otras sesiones **de la misma
  evaluación** ya finalizadas (línea base "poblacional o de cohorte", no
  el historial del propio estudiante — el capítulo es explícito en
  rechazar esto último).
- **Hallazgo empírico durante la construcción, no un placeholder inventado:**
  el primer intento usó `MIN_SESSIONS_FOR_MODEL = 8` y el modelo no
  detectaba ni un outlier 10x fuera de rango en las 5 dimensiones a la vez.
  Islando el problema con sklearn directo se confirmó la causa: la altura
  de árbol por defecto de `IsolationForest` es `ceil(log2(max_samples))`,
  y con 9 muestras esa altura (~4) es tan chica que ni siquiera separa un
  outlier extremo — cualquier punto más allá del máximo observado en el
  entrenamiento cae en la misma hoja "límite" que el propio máximo, sin
  importar cuán lejos esté (probado con valores 84.5, 90, 200, 902 y 5000:
  los cinco dieron el mismo score exacto). A partir de ~20 muestras el
  modelo separa de forma consistente. Se subió `MIN_SESSIONS_FOR_MODEL` a
  20 y se documentó el hallazgo en el propio código, porque es información
  real sobre el comportamiento del algoritmo, no un número arbitrario.
- También se filtran las columnas sin varianza en la población antes de
  entrenar (una feature constante, ej. sin eventos de mouse, solo diluye
  las divisiones aleatorias del bosque).
- Explicabilidad (RNF06): ya que Isolation Forest no da atribución de
  features nativa, se calcula el z-score de cada feature del target contra
  la población y se reportan las 2 más desviadas en `explanation`.
- Bug real encontrado y corregido en el camino: `IsolationForest.predict()`
  devuelve `numpy.bool_`, no `bool` de Python — `numpy.bool_(True) is True`
  da `False`, lo que rompía silenciosamente la lógica de
  `if result.is_anomalous`. Se corrigió casteando explícitamente.

**Prueba:** 24 tests de backend en verde, incluyendo 3 nuevos para
`anomaly.py` (población insuficiente → `None`; outlier claro detectado;
sesión típica no marcada) y 5 de integración nuevos
(`test_policy_and_traceability.py`): la política no se reinterpreta
retroactivamente, `item_ref` genera métricas por ítem, un indicador se
puede rastrear hasta la métrica real que lo originó (no solo el JSON), una
revisión puede apuntar a indicadores puntuales y rechaza IDs ajenos a la
sesión, y — el más costoso de construir — 21 sesiones sintéticas con
variación real en teclado y mouse más una sesión claramente distinta en
las tres dimensiones a la vez, verificando que el indicador
`atipico_modelo_poblacional` aparece. Se repitió también el flujo completo
a mano en el navegador (crear examen → rendir con un paste de 300
caracteres → ver el indicador con nivel "medio" y las métricas agrupadas
por ítem → marcar como revisada) y se confirmó por consulta directa a la
base que `policy_captures` e `indicator_metrics` quedaron pobladas.

**Qué no se hizo en este incremento (alcance acotado, ver pendientes):**
exponer en el dashboard un botón para versionar la política de un examen ya
creado (el endpoint existe y está testeado, falta la UI); Alembic para las
migraciones del nuevo esquema.

---

## Línea de base del 12/10/2026 (antes de los incrementos 6–8)

Se reconstruyó el MVP en un entorno limpio a partir del snapshot del 12/10
(que incluye los cambios sin commitear de `models.py`, `routers/sessions.py`,
`tests/test_api_flow.py`, `ExamsList.tsx` y `docker-compose.yml`; ver D04
del equipo) y se corrió todo antes de tocar nada:

- `pytest` → **25 passed** (los 24 del Incremento 5 + el test de idempotencia
  de lotes `test_duplicate_event_batch_is_not_double_inserted`, que venía con
  los cambios sin commitear: `Session.last_batch_seq` descarta un lote
  reenviado con el mismo `seq`). El README del backend todavía decía 24.
- `npm run build` del dashboard → OK (tsc + Vite 8, sin errores).
- **Hallazgo de entorno:** con Python 3.13 `pip install -r requirements.txt`
  falla (no hay wheels de `psycopg2-binary==2.9.9` ni `numpy==1.26.4` para
  3.13 y la compilación desde fuente no prospera). Con Python 3.12 instala
  y corre sin cambios; el `Dockerfile` usa 3.11. Recomendación: crear el
  venv con 3.11 o 3.12 hasta actualizar los pines.

---

## Incremento 6 — Evaluación reproducible con datos sintéticos

**Objetivo:** tener un procedimiento reproducible que calcule FAR, FRR,
AUC-ROC y EER del pipeline **real** del MVP (cap. 18, sección de métricas),
para validar el procedimiento antes de tener datos del piloto. Son **datos
sintéticos**: validan que la medición funciona de punta a punta y muestran
cómo responde el pipeline a anomalías de forma conocida; **no** son
resultados del piloto ni estiman el desempeño con estudiantes reales.

**Refactor previo (sin cambio de comportamiento):** para que la evaluación
mida exactamente el código que corre en la API, la decisión "métricas →
reglas + Isolation Forest → indicadores" se extrajo de
`routers/sessions.py::_run_processing` a una función pura,
`processing/pipeline.py::evaluate_session`, que ahora usan ambos. En
`anomaly.py` se separó "entrenar" (`fit_population_model`) de "puntuar"
(`score_with_model`); `score_against_population` sigue existiendo con la
misma firma. Un test verifica que entrenar una vez y puntuar N sesiones da
exactamente lo mismo que el camino de la API (el modelo usa
`random_state=0`). Los 25 tests previos siguieron en verde.

**Qué se construyó** (`backend/app/evaluation/` + `backend/scripts/evaluar.py`):
- `synthetic.py`: generador de sesiones con eventos crudos en el mismo
  formato que `capture.ts` (así se ejercita también `features.py`).
  Población normal con variación entre participantes y dentro de la sesión
  (dwell, flight, velocidad de mouse, pocos cambios de pestaña, pegados
  chicos ocasionales). Cuatro perfiles anómalos: `pegado_masivo`,
  `cambio_pestana`, `tecleo_automatizado` (pensados alrededor de los
  umbrales de las reglas) y `ritmo_distinto` (teclado y mouse desplazados
  `dificultad` desvíos poblacionales, sin señales discretas: solo lo puede
  ver el Isolation Forest). Todos los parámetros son explícitos
  (`SyntheticParams`) y se imprimen en el reporte, siguiendo la
  recomendación de Emmott et al. (2013) para benchmarks de anomalías
  (ficha `equipo/investigacion/T05_evaluacion.md`). Los valores **no están
  calibrados con personas reales**.
- `metrics.py`: convención fijada con la ficha T05 — clase positiva =
  sesión anómala; **FAR = anomalías no detectadas (FN/P)**, **FRR = falsas
  alarmas (FP/N)**; EER por interpolación sobre la curva ROC; AUC-ROC y
  *average precision* (recomendada con clases desbalanceadas). El score
  continuo es `-decision_function` del Isolation Forest; las reglas son
  binarias y aportan un único punto de operación.
- `experiment.py`: protocolo por repetición (semilla fija por repetición):
  población de 40 sesiones normales de la misma evaluación → se entrena el
  modelo una vez → 40 normales + 40 anómalas de prueba, disjuntas → cada una
  pasa por `compute_all_features` + `evaluate_session`. Los umbrales y
  `contamination=0.1` se evalúan tal como están en el código, **sin
  ajustarlos mirando las etiquetas** (Goldstein & Uchida 2016). Se reporta
  media, desvío y percentiles 2,5–97,5 entre 20 repeticiones.
- `scripts/evaluar.py`: CLI que corre el protocolo, un **barrido de
  dificultad** para `ritmo_distinto` (0 a 3 σ) y un **análisis de
  sensibilidad** con la población contaminada con 10 % de anómalas, y
  escribe en `docs/evaluacion/`: `resultados_sinteticos.md` (reporte
  legible, se sube al proyecto), `barrido_dificultad.csv` y `roc_modelo.csv`
  (sirven para graficar con pgfplots), más `resultados_sinteticos.json` y
  `sesiones_sinteticas.csv` (se regeneran, no se suben). Tarda ~5 min.

**Bug del generador encontrado al leer los resultados (y corregido):** en
la primera versión, `ritmo_distinto` fijaba la media de cada participante
en exactamente μ + kσ, sin variación entre participantes. Con k chico eso
hacía a las sesiones "anómalas" *más centrales* que las normales y el
barrido daba AUC = 0,23 con k = 0,5 (peor que el azar), lo que no tiene
sentido para un desplazamiento positivo. Se corrigió sumando el
desplazamiento a la variación normal entre participantes; ahora con k = 0
el perfil es indistinguible de lo normal (AUC = 0,49, como debe) y el AUC
crece de forma monótona con k. Hay un test que fija ese comportamiento.

**Resultados con la configuración por defecto** (20 repeticiones,
dificultad 2 σ; detalle completo en `docs/evaluacion/resultados_sinteticos.md`):

| Componente | FAR (no detectadas) | FRR (falsas alarmas) |
|---|---|---|
| Pipeline completo | 3,6 % ± 4,2 | 11,7 % ± 6,7 |
| Solo reglas | 25,0 % (no ven `ritmo_distinto`) | 0,0 % |
| Solo Isolation Forest | 65,0 % ± 10,8 | 11,7 % ± 6,7 |

Barrido de `ritmo_distinto` (solo modelo): AUC 0,49 / 0,56 / 0,70 / 0,84 /
0,93 / 0,99 y EER 0,51 / 0,47 / 0,35 / 0,24 / 0,14 / 0,05 para
k = 0 / 0,5 / 1 / 1,5 / 2 / 3 σ.

**Lectura (para cap. 17/18):**
- La FRR del Isolation Forest (~11,7 %) queda cerca de `contamination=0.1`
  **por construcción**: es una tasa de revisión fijada por diseño, no una
  tasa de fraude estimada (coincide con lo que anticipaba la ficha T05).
- Que las reglas detecten el 100 % de sus perfiles es una verificación de
  que se disparan cuando corresponde, no evidencia de desempeño: esos
  perfiles se construyeron alrededor de los umbrales.
- El AUC "global" del modelo (0,67) es bajo porque incluye perfiles que el
  modelo no tiene forma de ver (pegado, pestañas); lo informativo es el
  AUC por perfil y el barrido.
- Con la población contaminada al 10 % la FRR baja a ~7 % (parte del 10 %
  de `contamination` lo "ocupan" las anómalas de entrenamiento) y el AUC
  para `ritmo_distinto` casi no cambia (0,94).

**Prueba:** 15 tests nuevos (`tests/test_evaluation.py`): FAR/FRR con la
convención documentada, EER = 0 con separación perfecta, = 1 con scores
invertidos, ≈ 0,5 sin información y = 0,25 en un caso calculado a mano;
reproducibilidad del generador con la misma semilla; formato de eventos
igual al de `capture.ts` y sin contenido (RNF01); cada perfil cruza el
umbral para el que fue diseñado; las sesiones normales casi nunca disparan
reglas (≤ 2 de 50); el desplazamiento de `ritmo_distinto` crece con la
dificultad; equivalencia "entrenar una vez / puntuar muchas" con el camino
de la API; corrida chica de punta a punta determinística.

**Pendiente:** cuando haya datos del piloto, reemplazar el generador por
las métricas de sesiones reales etiquetadas (anómalas simuladas del diseño
del piloto) y reusar `metrics.py`/`experiment.py`; intervalos *bootstrap*
sobre una única muestra real (con datos sintéticos alcanza con repetir).

---

## Incremento 7 — Capturas de demo automatizadas + dos correcciones de UI

**Objetivo:** tener capturas reales del flujo de punta a punta para el
capítulo de Desarrollo del MVP, regenerables con un solo comando.

**Qué se construyó:**
- `backend/scripts/seed_demo.py`: puebla una evaluación con N sesiones
  sintéticas (y opcionalmente sesiones `ritmo_distinto`) **a través de la
  API HTTP real** (`start` → `events` → `end`). Los participantes se llaman
  `SINT-###` para que en el dashboard quede a la vista que no son personas.
  Sirve para que la demo tenga línea base poblacional (≥ 20 sesiones) y el
  indicador del Isolation Forest pueda aparecer.
- `mvp/scripts/capturas_demo.py`: levanta backend (SQLite temporal) +
  dashboard (`vite preview` en el puerto 5173, el que permite CORS),
  recorre el flujo con Playwright/Chromium y guarda PNG numeradas en
  `docs/capturas/`. El tecleo del estudiante se simula con tiempos de
  pulsación y entre teclas variables, porque `keyboard.type` de Playwright
  tiene dwell ≈ 0 ms (el pipeline lo marcaría, correctamente, como
  `ritmo_tecleo_atipico`). El pegado dispara el evento `paste` real del DOM.
  Las PNG **no** se suben al proyecto (no guarda binarios): se regeneran en
  local con `python scripts/capturas_demo.py` (ver README).

**Capturas que genera** (`docs/capturas/`):

| Archivo | Qué muestra | Requisitos |
|---|---|---|
| `01_login_docente.png` | Login del panel docente | — |
| `02_crear_evaluacion.png` | Formulario de nueva evaluación: info previa, reglas, consigna y señales habilitadas | RF01, RF02, RF04 |
| `03_evaluacion_creada.png` | Confirmación con el código y el enlace para estudiantes | — |
| `04_estudiante_info_y_consentimiento.png` | Vista del estudiante antes de empezar: qué se registra (texto del docente + lista de señales habilitadas con su descripción precisa, desde el Incremento 10), reglas, código de participante y consentimiento (sin la consigna) | RF01, RF02, HU01, HU02, RNF02 |
| `05_estudiante_rindiendo.png` | Consigna + respuesta en curso, estado de sincronización | RF03, RNF07 |
| `06_estudiante_entrega.png` | Confirmación de entrega | — |
| `07_sesiones_de_la_evaluacion.png` | Lista de sesiones con indicadores y estado de revisión docente | RF06, RF07 |
| `08_sesiones_filtro_requiere_revision.png` | Filtro "solo sesiones que requieren revisión" | RF07, RNF08 |
| `09_detalle_sesion_indicadores.png` | Detalle de la sesión del estudiante: indicadores con métrica de origen y umbral, métricas calculadas | RF08, RF09, RF10, RNF05, RNF06 |
| `10_revision_docente_registrada.png` | Pedido de validación adicional con nota, ligado a un indicador | RF11, HU08 |
| `11_detalle_atipico_modelo_poblacional.png` | Sesión sintética `ritmo_distinto` marcada por el Isolation Forest, con su posición relativa en la línea base y las dos métricas más desviadas (desde el Incremento 10, sin el valor crudo del score) | RNF06, cap. 15 IA |
| `12_validaciones_pendientes.png` | Vista de validaciones adicionales pendientes (Incremento 8) | RF11, HU08 |
| `13_historial_de_revision.png` | Historial: pedido de validación + cierre posterior, sin editar el anterior | RF10, RF11, RNF04 |
| `14_politica_edicion.png` | Edición de la política de captura (crea versión nueva) | RF01, RF02, RF04, RNF04 |
| `15_politica_version_2.png` | Política vigente en versión 2 | RNF04 |
| `16_detalle_captura_incompleta.png` | (la genera `scripts/prueba_red.py --capturas DIR`, Incremento 10) Sesión con un corte de red prolongado: aviso informativo `captura_incompleta`, "Solo avisos informativos" en lugar de "Requiere revisión" | cap. 15 Captura de señales, RNF04 |

**Lo que mostró la demo, tal cual salió** (no está arreglado para que
"quede bien"): la sesión del estudiante (`EST-DEMO-01`) dispara
`paste_volume_alto` (461 caracteres pegados, umbral 200) y **además**
`atipico_modelo_poblacional` por la velocidad del mouse (en la corrida
revisada, z ≈ 12 en `std_mouse_speed_px_ms`). Esto último es un artefacto de mezclar una
sesión de navegador con una línea base sintética: el movimiento de mouse
de Playwright (y, presumiblemente, el de una persona) es mucho más
irregular que el del generador. Refuerza que los parámetros sintéticos no
representan a usuarios reales y que la línea base tiene que salir de
sesiones reales del mismo examen.

**Dos correcciones de UI encontradas al mirar las capturas:**
- **Horas corridas −3 h.** La base guarda `datetime.utcnow()` (sin zona) y
  la API lo devolvía sin offset; el navegador lo interpretaba como hora
  local. Ahora todas las fechas de la API salen con `+00:00`
  (`schemas.datetime_utc`) y el dashboard las formatea con
  `format.ts::formatDateTime` (que además fuerza reloj de 24 h: `es-AR`
  mostraba 12 h sin "a. m./p. m."). Test nuevo:
  `test_api_timestamps_are_explicit_utc`.
- **Nombres de indicador en crudo** ("Paste Volume Alto"): ahora se
  muestran etiquetas legibles ("Volumen de texto pegado alto", "Patrón
  atípico frente a la línea base poblacional", etc.).

**Prueba:** el script corre de punta a punta y genera las 15 capturas; se
revisaron visualmente. 41 tests de backend en verde a esta altura; build y
`oxlint src` del dashboard sin errores.

---

## Incremento 8 — Validación adicional pendiente (RF11/HU08) y versionado de política desde la UI

**RF11/HU08 — "profundizar el caso".** Antes, "Requiere validación
adicional" solo guardaba una `Review` y no había forma de ver qué casos
seguían abiertos. Cap. 13 aclara que ImprontIA *indica* la validación pero
no la ejecuta; por eso no se agregó ningún "mecanismo" de validación, solo
seguimiento:
- **Estado de revisión derivado, no guardado:** `sin_revision` /
  `revisada` / `validacion_pendiente`, calculado a partir de la **última**
  `Review` de la sesión. Como las revisiones son solo inserción, cerrar un
  pedido no edita el anterior: se agrega una revisión "Marcada como
  revisada" y el historial conserva ambas (RF10, RNF04).
- API: `SessionSummary` incluye `exam_name`, `review_status`,
  `last_review_at` y `last_review_notes`; `GET /sessions` acepta
  `review_status` (combinable con `exam_id`; sin `exam_id` lista todas las
  evaluaciones del docente); `SessionDetail` trae `reviews` (historial con
  el email del docente y los indicadores atendidos).
- Dashboard: nueva vista `/validaciones` (`PendingValidations.tsx`) con
  contador en la barra superior; columna "Revisión docente" en la lista de
  sesiones; historial de revisiones en el detalle, que se refresca al
  registrar una revisión.
- Decisión de alcance: el filtro por estado se resuelve en memoria sobre
  las sesiones del docente. Alcanza para el volumen de una cátedra; con
  más volumen (RNF09) habría que resolverlo en SQL o materializarlo.

**T11 — versionar la política desde el dashboard.** El endpoint existía
desde el Incremento 5; faltaba la UI. `PolicyCard.tsx` (en la página de
sesiones de cada evaluación) muestra la política vigente y su número de
versión (`ExamOut.policy_version`, nuevo) y permite editarla: guardar crea
la versión N+1 y la UI aclara que las sesiones ya iniciadas conservan la
que aceptaron.

**Prueba:** 6 tests nuevos (`tests/test_review_status.py`: el estado sigue
a la última revisión y el historial se conserva; la vista de pendientes
cruza evaluaciones, excluye las cerradas y las no revisadas y se combina
con `exam_id`; filtro inválido → 400; no se filtran sesiones de otro
docente. En `test_policy_and_traceability.py`: contador de versión y
política vigente tras versionar; versionar exige ser dueño del examen).
**47 tests en verde**; `npm run build` y `oxlint src` OK; el recorrido de
capturas cubre ambas funciones (capturas 12 a 15).

---

## Incremento 9 — Prueba interna end-to-end, diagramas y ajustes de privacidad de la captura

**Contexto:** por la decisión D03 del equipo no hay piloto con voluntarios en
la entrega; la evaluación se apoya en los datos sintéticos (Incremento 6) y en
una **prueba interna de punta a punta** sobre el sistema real (T18). En la
misma corrida se hicieron los diagramas funcionales que pide la rúbrica (T25)
y se corrigieron tres desvíos de la captura señalados al redactar el cap. 17.

**Prueba interna** (`scripts/prueba_interna.py`, resultados e interpretación
en `docs/evaluacion/prueba_interna.md`):
- Levanta backend + dashboard reales con una base SQLite temporal y, con
  Playwright/Chromium, rinde sesiones desde la vista del estudiante con
  cuatro guiones: `normal`, `pegado_masivo` (461 caracteres), `cambios_foco`
  (7 salidas de pestaña) y `transcripcion` (ritmo constante: 80 ms de
  pulsación, 110 ms entre teclas). Cada escenario corre en una evaluación
  nueva con la misma línea base de 24 sesiones sintéticas (vía API).
- Verifica: indicadores de la API frente a los esperados; que la vista
  docente del dashboard muestre la misma cantidad de indicadores y el mismo
  estado; que ningún evento persistido contenga texto de la respuesta ni del
  pegado; y, tras el ajuste de abajo, que los eventos de teclado no
  identifiquen la tecla. Calcula además el *z-score* de cada métrica continua
  frente a la línea base (la API solo expone el puntaje del IF si marca).
- Escribe `prueba_interna.csv`, `prueba_interna_resultados.md` (tablas
  generadas) y `prueba_interna.json` (no se versiona); `--capturas DIR`
  guarda el detalle docente de cada sesión.
- **Limitación encontrada al construirla:** Playwright fija la página como
  visible (emula el foco); ni con navegador visible bajo Xvfb, ni con otra
  pestaña al frente, ni minimizando la ventana por CDP se dispara
  `visibilitychange`. El escenario de cambios de foco lo simula
  sobrescribiendo `document.visibilityState` y despachando el evento nativo;
  el listener real de `capture.ts` lo registra. El cambio de pestaña real
  queda cubierto por `docs/evaluacion/protocolo_prueba_manual.md` (15 min,
  para que Martina/Juan lo repitan a mano).

**Resultados** (dos corridas de 4 escenarios × 3 repeticiones):
23/24 sesiones conformes; 24/24 con dashboard = API; 24/24 sin texto en los
eventos; el Isolation Forest no marcó ninguna de las 24.
- **Hallazgo (regla de ritmo uniforme):** en dos sesiones `transcripcion`,
  128 de 129 pulsaciones midieron 85–93 ms y **una** midió 189 ms (corrida 1)
  o 141 ms (corrida 2). Esa sola pulsación subió el desvío de ≈ 1,5 ms a
  9,1 ms (la regla de < 5 ms **no** se disparó) y a 4,9 ms (se disparó por
  0,1 ms). El desvío estándar no es robusto y el umbral está en el orden del
  ruido de medición; además, todas las pulsaciones se miden ≈ 7 ms más
  largas que lo ordenado (latencia de la cadena de eventos). **No se cambió
  la regla** para no invalidar los resultados sintéticos ya incorporados al
  documento; queda como trabajo futuro (rango intercuartílico o MAD +
  calibración del umbral).
- **El IF no marcó `transcripcion` pese a z ≈ −4,5** en el desvío de
  pulsación: un valor fuera del rango de entrenamiento puntúa igual que el
  extremo observado (mismo fenómeno del Incremento 5) y con un solo rasgo
  desviado de cinco no alcanza el corte del 10 %. La regla y el modelo se
  complementan.
- En `cambios_foco` el tiempo entre teclas sube a ≈ 270 ms porque las pausas
  fuera de la pestaña quedan dentro de `keyup → keydown` (trabajo futuro:
  excluirlas).

**Ajustes de privacidad en la captura** (pedidos del Redactor, desvíos 1, 2 y
4 del cap. 17 §Limitaciones), aplicados entre la corrida 1 y la 2:
1. `capture.ts` **ya no envía qué tecla se pulsó** (`code`): la secuencia de
   teclas físicas permitía reconstruir aproximadamente el texto, en contra de
   RNF01 y de lo que dice el cap. 15 ("el evento nunca persiste el carácter
   tipeado"). El backend no necesitó cambios: `features.py` ya emparejaba
   keydown/keyup en orden de llegada cuando falta `code` (una sola cola
   FIFO), lo que es exacto mientras las teclas se suelten en el orden en que
   se presionaron, incluso solapadas. Dos tests nuevos: el emparejamiento sin
   `code` da lo mismo que por tecla con teclas solapadas, y las features de
   las sesiones sintéticas no cambian al quitar `code` (el generador no
   solapa teclas), así que **los resultados del Incremento 6 siguen
   valiendo**. La corrida 2 de la prueba interna verifica sobre la base real
   que ya no se guarda y que los tiempos medidos no cambian (diferencias
   ≤ 1,1 ms de media entre corridas).
2. Una política **sin señales habilitadas ya no captura nada** (antes una
   lista vacía habilitaba todas): minimización por defecto.
3. La vista del estudiante pide un **código de participante** seudónimo
   ("no ingreses tu nombre ni tu legajo") en lugar de sugerir el legajo.
   Los selectores de `capturas_demo.py` y `prueba_interna.py` se ajustaron.

**Diagramas funcionales (T25)**, en TikZ dentro de la tesis
(`latex/figures/diagramas/`): componentes (módulos reales del frontend y del
backend, protocolos y autenticación de cada canal), flujo de información
como diagrama de secuencia (cinco fases, de la información previa al
consentimiento a la revisión docente, con los *endpoints* y tablas reales;
lo genera `gen_flujo_informacion.py`) y clases del dominio (transcripción
de `models.py` con multiplicidades). Requieren una línea en el preámbulo:
`\usetikzlibrary{arrows.meta,positioning,fit,calc,backgrounds,shapes.multipart}`
(cargarla dentro de un `figure` no alcanza: queda local al grupo).

**Repo para la entrega (T30):** README raíz y de `mvp/`, `backend/` y
`dashboard/` actualizados (el README raíz todavía describía una extensión de
Chrome); `.gitignore` de la raíz ampliado con Python, Node, bases SQLite,
`.env` y salidas regenerables (el del repo solo cubría LaTeX).

**Prueba:** `pytest` → **49 passed** (47 + 2 nuevos de emparejamiento sin
`code`); `npm run build` y `npx oxlint src` sin errores; `prueba_interna.py`
corrido dos veces completo (≈ 9,6 min cada una); los tres diagramas
compilados con `pdflatex` sobre el preámbulo de `main_full.tex`, sin errores
ni cajas desbordadas, y revisados visualmente.

---

## Incremento 10 — Cierre de los desvíos pendientes respecto del cap. 15

**Contexto:** el cap. 17 §Limitaciones dejaba tres "desvíos pendientes
respecto de la especificación": (a) la longitud del pegado se obtiene
leyendo un instante el portapapeles y eso no se le declaraba al estudiante;
(b) el nivel del indicador del modelo se decidía con un corte fijo del score
y no con percentiles sobre la muestra; (c) la sincronización reintentaba
cada 5 s fijos, sin *backoff*, sin límite de buffer y sin registrar el
agotamiento del buffer ni una falla persistente. Al revisar el código para
cerrarlos aparecieron dos desvíos más, no listados:
(d) el detalle docente mostraba el **valor crudo del score** del Isolation
Forest ("puntaje de atipicidad: −0,034"), cuando el cap. 15 dice que no se
expone al docente ni el score crudo ni una cifra de probabilidad; y
(e) `capture.ts` leía el texto del portapapeles **antes** de aplicar el
filtro de señales habilitadas, es decir, también en evaluaciones sin la
categoría "portapapeles" (no se guardaba ni se enviaba, pero se leía).
Los cinco se corrigieron en este incremento; ninguno cambia los resultados
de la evaluación sintética ni de la prueba interna ya citados en el
documento (verificado, ver "Prueba").

**(b) Nivel del indicador del modelo por percentiles** (`anomaly.py`,
`indicators.py`). El cap. 15 pide que las categorías baja/media/alta "se
calibran mediante percentiles sobre la distribución del score en la muestra
general usada como línea base (por ejemplo, ubicando el corte de 'alta' en
el extremo más atípico de esa distribución)". Ahora:
- `fit_population_model` guarda los scores de la propia población de
  entrenamiento y `score_with_model` devuelve `population_percentile`: la
  proporción de sesiones de la línea base igual o más atípicas que la
  evaluada (0 = más atípica que todas).
- El modelo sigue marcando con la misma frontera (`contamination=0.1`, en
  torno al percentil 10 de la población); entre las marcadas, las que caen
  en el **5 % más atípico** (`PERCENTILE_HIGH = 0.05`) reciben nivel alto y
  el resto medio. Las no marcadas equivalen a atipicidad baja y no generan
  indicador. El 0,05 es provisorio, como los demás umbrales.
- **Efecto medido sobre los datos sintéticos** (protocolo por defecto del
  Incremento 6, 20 repeticiones, 374 sesiones marcadas por el modelo): con
  el corte fijo anterior (score < −0,1) solo 31 recibían nivel alto, todas
  anómalas; con percentiles reciben nivel alto 246 (197 anómalas y 49
  normales). Las 49 normales son el 6,1 % de las 800 normales de prueba,
  cerca del 5 % que fija el corte **por diseño**: igual que
  `contamination`, el nivel alto pasa a tener un significado explícito
  ("dentro del 5 % más atípico de esta evaluación") en lugar de depender de
  la escala del score, que varía con la población. Con un corte de 2,5 %
  quedarían 36 normales y 169 anómalas. Se mantiene 5 % porque es lo que
  describe el cap. 15; calibrarlo es parte del piloto.
- La explicación del indicador agrega `population_percentile`,
  `population_size` y el corte usado; `anomaly_score` se conserva para
  trazabilidad pero **no se muestra** (ver d).

**(d) Sin score crudo en el dashboard** (`SessionDetail.tsx`). El detalle
del indicador del modelo ahora dice, por ejemplo, "Se ubica dentro del 5 %
más atípico de las 24 sesiones de esta evaluación usadas como línea base"
(o "Resultó más atípica que las 24 sesiones…" en el extremo) y enumera los
factores en palabras: "Velocidad media del mouse (px/ms): 1,25 (media
poblacional: 0,61, 4,2 desvíos por encima)". Es la forma que propone el
cap. 15: categoría relativa a la muestra + factores que más contribuyeron.

**(c) Sincronización con backoff, buffer acotado y eventos de estado**
(`dashboard/src/syncQueue.ts`, nuevo; `TakeExam.tsx`):
- La lógica de la cola se separó en un módulo puro (`SyncQueue`), sin DOM ni
  red, para poder probarla. `TakeExam.tsx` pasó de un `setInterval` fijo a
  una cadena de `setTimeout` cuyo intervalo es 5 s sin fallas y
  `5 s × 2^fallas` con ±20 % de variación aleatoria y tope de 60 s (la
  variación evita que muchos estudiantes que pierden la red a la vez
  reintenten sincronizados).
- **Buffer acotado** a 20 000 eventos (buffer + lotes pendientes; con
  teclado y mouse, unos 20 minutos sin conexión). Si se llena, se conserva
  lo más antiguo, se descartan los eventos nuevos y se cuentan con su rango
  temporal; al reconectar se agrega un evento propio
  `buffer_overflow {dropped, from_t, to_t}`.
- **Falla persistente:** desde 3 intentos consecutivos fallidos, al
  recuperar la conexión se agrega un evento propio
  `sync_failure {failed_attempts, duration_ms}` con la marca temporal de la
  primera falla. Cortes más breves no dejan registro.
- Si el navegador avisa que volvió la conexión (`online`), se reintenta
  enseguida en lugar de esperar el próximo intento del backoff. Al
  finalizar se reintenta hasta 3 veces (1, 2 y 4 s); si quedan registros
  sin enviar, la pantalla final se lo dice al estudiante en vez de
  confirmar que la sesión quedó registrada. Mientras no hay conexión, el
  estudiante ve "sin conexión — N lote(s) pendientes, reintentando en X s.
  Podés seguir escribiendo…".
- Backend (`features.py`, `indicators.py`, `pipeline.py`): dos métricas
  nuevas, `capture_dropped_events` y `sync_failure_count`
  (`compute_capture_integrity`), y un indicador **informativo**
  `captura_incompleta` (nivel bajo, vinculado a esas métricas por la
  relación N:M). Decisión: **no prioriza la sesión** — una mala conexión
  no es un indicio sobre la conducta del estudiante; `IndicatorDraft`
  ganó el campo `prioritizes_review` y `needs_review` pasó a ser "hay al
  menos un indicador que prioriza". El detalle lo muestra con otro color,
  con la leyenda "este aviso no prioriza la sesión para revisión", y el
  encabezado dice "Solo avisos informativos" si es el único. Los eventos de
  estado de la captura no cuentan para la duración ni la inactividad de la
  sesión.

**(a) y (e) Declaración del pegado y lectura solo si está habilitado**
(`format.ts`, `TakeExam.tsx`, `capture.ts`). Antes del consentimiento, el
estudiante ve, además del texto libre del docente, la **lista de señales
habilitadas** generada a partir de la misma `allowed_signals` que limita la
captura (RNF02: lo informado y lo capturado no pueden divergir aunque el
texto del docente sea impreciso), cada una con su descripción exacta. La de
portapapeles dice: "De lo que pegás solo se registra la cantidad de
caracteres: el texto se lee un instante en tu navegador para contarlo y no
se guarda ni se envía". La de teclado: "No se registra qué tecla es ni el
texto que escribís". Una política sin señales muestra "En esta evaluación
no se registra ninguna señal de interacción". Y `onPaste` ahora verifica
que la categoría esté habilitada **antes** de leer el portapapeles.

**Detalles menores:** `index.html` del dashboard con `lang="es"` y título
"ImprontIA" (decía "en" y "dashboard").

**Prueba:**
- `pytest` → **55 passed** (49 + 6 de `tests/test_incremento10.py`:
  percentil de la sesión en la línea base, nivel por banda y no por score
  absoluto, métricas de integridad que no cuentan como actividad, indicador
  informativo que no prioriza, y el flujo completo por la API con un
  `sync_failure` hasta el indicador vinculado a su métrica).
- **Primeras pruebas unitarias del frontend:** `npm test` (`node --test` con
  eliminación de tipos, sin dependencias nuevas) → 6/6 en
  `dashboard/tests/syncQueue.test.ts`: backoff y su tope, orden y número de
  lote, buffer lleno → `buffer_overflow`, falla breve vs. persistente →
  `sync_failure`, y que los eventos de estado entran con el buffer lleno.
  `npm run build` y `npx oxlint src tests` sin hallazgos.
- **Prueba de resiliencia end-to-end** (`scripts/prueba_red.py`, nuevo;
  resultados en `docs/evaluacion/prueba_red.md`): tres escenarios sobre el
  sistema real, conformes en la corrida vigente. Se corrió cuatro veces
  durante el desarrollo (las dos primeras sin el escenario de reconexión,
  que se agregó junto con el reintento por `online`); en la primera, la
  verificación del buffer exigía exactamente 5 000 descartados y hubo 5 002,
  porque en el instante del corte quedaban 2 eventos sin enviar: se corrigió
  la verificación (lo exigible es guardados + descartados = capturados), no
  el código. Corte prolongado:
  intentos a 5,0 / 9,4 / 18,1 / 44,0 s (esperado 5/10/20/40 ± 20 %), 80
  pulsaciones tipeadas y 80 guardadas, un `sync_failure` y
  `captura_incompleta` sin "Requiere revisión". Buffer lleno: 20 039
  guardadas + 5 001 descartadas registradas = 25 040 capturadas.
  Reconexión avisada: resincroniza en 0,1 s.
- **Los resultados ya citados no cambian:** el protocolo sintético por
  defecto se volvió a correr con el código nuevo y dio exactamente lo
  mismo (pipeline FAR 3,6 % ± 4,2, FRR 11,7 % ± 6,7; AUC del modelo 0,669):
  el nivel no interviene en la decisión de marcar, el generador no produce
  eventos de estado y los indicadores informativos no existen en esas
  sesiones. La prueba interna (Incremento 9) no envía eventos de estado y
  su verificación de estado del dashboard ("Requiere revisión" / "Sin
  indicadores") sigue valiendo para sus 4 escenarios.
- `capturas_demo.py` corrido completo con el código nuevo: 15/15 capturas;
  se revisaron la 04 (lista de señales) y la 11 (percentil y factores en
  palabras, sin score). `prueba_red.py --capturas` genera la 16.

**Qué quedó pendiente:** el buffer vive en la memoria de la pestaña (si el
estudiante la cierra sin conexión, lo pendiente se pierde; persistirlo en el
navegador queda para cuando se defina la retención, RNF10); la capacidad de
20 000 eventos y el umbral de 3 fallas son valores de diseño sin calibrar.

---

## Incremento 11 — Cierre de los hallazgos de la revisión para la entrega (14/10)

**Contexto:** las revisiones del 13/10 y del 14/10 (`equipo/revision/`)
asignaron al desarrollo cinco hallazgos: **A9** (la prueba interna no se
había vuelto a correr con el código del Incremento 10), **M5** (el
generador sintético todavía emitía `code`), **M7** (dos diagramas
atribuían la escritura en la base a módulos que son funciones puras, y al
de componentes le faltaban `Login.tsx` y el uso de `api.ts` por parte del
estudiante), **M4** (confirmar los parámetros de los perfiles sintéticos
para el cap. 18) y **B11** (`datetime.utcnow()` deprecado), más una
referencia rota en `index.html`. Al correr las pruebas apareció además un
error en los scripts de prueba que afectaba al pasaje a la Mac. Ninguno
de los cambios altera resultados ya citados en el documento (verificado
byte a byte, ver "Prueba").

**A9 — Prueba interna sobre el código entregado (corrida 3).**
`prueba_interna.py` se volvió a correr completo (4 escenarios × 3
repeticiones, mismo guion, semillas y línea base) con el código del
Incremento 10: **12/12 conformes**, 12/12 dashboard = API, 12/12 sin texto
en los eventos ni identificación de la tecla, IF 0/12. Acumulado de las
tres corridas: 35/36 conformes. Los eventos por escenario son idénticos a
los de las corridas anteriores (301 / 122 / 325 / 297), lo que indica que
la cola de sincronización nueva no pierde ni agrega eventos sin cortes de
red. En `transcripcion` no hubo pulsaciones demoradas (desvío 1,3 / 2,1 /
2,4 ms), lo que confirma que los dos casos límite de las corridas 1 y 2
dependían de un evento aislado y no del guion. La corrida 3 pasa a ser la
vigente (`prueba_interna_resultados.md`, `prueba_interna.csv`); la 2 se
conserva como `prueba_interna_corrida2_*` y la 1 como
`prueba_interna_corrida1_*`. Interpretación actualizada en
`docs/evaluacion/prueba_interna.md`.

**M5 — Generador sintético sin `code`** (`app/evaluation/synthetic.py`).
Los eventos de teclado sintéticos ahora tienen solo `t` y `type`, igual
que los de `capture.ts` desde el Incremento 9. Para no mover ningún número
publicado, **se conserva el sorteo** que elegía la tecla (se descarta el
valor): así la secuencia de números aleatorios es la misma y las sesiones
generadas con cada semilla son idénticas salvo por la clave `code`. Como el
generador nunca solapa teclas, el emparejamiento en orden de llegada da los
mismos tiempos de pulsación. Verificación:
- El protocolo por defecto de `scripts/evaluar.py` (20 repeticiones +
  barrido + sensibilidad) se corrió antes y después del cambio:
  `resultados_sinteticos.json`, `sesiones_sinteticas.csv`, `roc_modelo.csv`
  y `barrido_dificultad.csv` salieron **idénticos byte a byte**, y
  `barrido_dificultad.csv` coincide además con el publicado en el proyecto
  el 12/10. Pipeline FAR 3,6 %, FRR 11,7 %; AUC del modelo 0,669.
- El test que comparaba con y sin `code` se reemplazó por uno más fuerte:
  fija, para la semilla 3, la cantidad de eventos y cuatro métricas
  calculadas con el generador **anterior**, y exige que el generador nuevo
  dé exactamente esos valores sin emitir `code`. El test de formato exige
  que las pulsaciones tengan solo `t` y `type`.

**M7 — Diagramas fieles a quién persiste** (`latex/figures/diagramas/`).
En el código, `routers/sessions.py::_run_processing` lee los eventos y la
línea base de la base de datos, llama a
`features.compute_all_features`, `anomaly.fit_population_model` y
`pipeline.evaluate_session` (que compone las reglas de `indicators.py` y el
puntaje de `anomaly.score_with_model`) y escribe `Metric`, `Indicator`,
`IndicatorMetric` y `needs_review`. Los módulos de `processing/` no tocan
la base. Cambios:
- `componentes.tex`: `processing/` aparece como un subgrupo "funciones
  puras, sin acceso a la base" llamado por el router al finalizar la
  sesión; la flecha de persistencia sale de `routers/sessions.py` hacia el
  ORM ("lee eventos y línea base / persiste métricas e indicadores"); el
  navegador del estudiante incluye `api.ts` (endpoints públicos y token de
  sesión), por donde salen las llamadas de `TakeExam.tsx`; la lista de
  vistas del docente incluye `Login`.
- `flujo_informacion.tex` (regenerado con `gen_flujo_informacion.py`): la
  fase 4 ahora muestra a la API leyendo los `Event`, pidiendo las métricas
  al procesamiento, guardando `Metric`, leyendo la línea base, pidiendo la
  evaluación y guardando `Indicator` + `IndicatorMetric`; el procesamiento
  solo devuelve resultados ("funciones puras").
- Ambos compilados con el preámbulo de `main_full.tex` (clase `book` 12 pt,
  `babel` español, `mathptmx`, mismas bibliotecas TikZ y colores): sin
  errores, sin cajas desbordadas y sin "float too large" (el de secuencia
  se compactó levemente para seguir entrando en una página: 22,6 cm de
  alto). Revisados visualmente.

**M4 — Parámetros de los perfiles sintéticos (para el cap. 18).** Valores
exactos de `SyntheticParams` y `generate_session`, con la notación del
código (los intervalos de enteros de numpy excluyen el extremo superior):

| Perfil | Parámetros |
|---|---|
| normal | Por participante: pulsación media ~ N(95; 15) ms (mín. 40), desvío dentro de la sesión ~ U(15; 30) ms; tiempo entre teclas medio ~ N(160; 35) ms (mín. 50), desvío ~ U(40; 80) ms; velocidad media del mouse ~ N(0,6; 0,15) px/ms (mín. 0,1), CV dentro de la sesión 0,3. Por sesión: 250–499 pulsaciones; 60–149 movimientos de mouse, separados 100–400 ms; clic final con prob. 0,8; cambios de pestaña ~ Poisson(0,6) con duración ~ Exp(media 4 000 ms); pegado chico con prob. 0,2 (5–59 caracteres); copias ~ Poisson(0,3). |
| `pegado_masivo` | Pulsaciones = máx(30; 30 % de las de la sesión normal); 1–3 pegados que suman 400–2 000 caracteres (reparto multinomial). |
| `cambio_pestana` | 6–12 cambios de pestaña con duración ~ Exp(media U(5 000; 15 000) ms). |
| `tecleo_automatizado` | Desvío de la pulsación ~ U(0,5; 3) ms y del tiempo entre teclas ~ U(0,5; 5) ms. |
| `ritmo_distinto` | Medias de pulsación, tiempo entre teclas y velocidad del mouse desplazadas k desvíos entre participantes (+15 ms, +35 ms y +0,15 px/ms por unidad de k); k = 2 por defecto, 0–3 en el barrido. |

**B11 — Fechas sin la API deprecada** (`models.py`, `auth.py`,
`routers/sessions.py`, `schemas.py`). `datetime.utcnow()` está deprecado
desde Python 3.12 y producía más de 4 000 avisos al correr `pytest`. Se
reemplazó por `models.utcnow()`, que devuelve exactamente lo mismo que se
guardaba (hora UTC sin zona), así que la serialización con `+00:00` del
Incremento 7 y los datos existentes no cambian; el vencimiento del JWT se
calcula con una fecha con zona. De paso, los tres `class Config` de
Pydantic pasaron a `model_config = ConfigDict(from_attributes=True)`.
Resultado: de **4 387 avisos a 53**, todos de dependencias de terceros
(`python-jose`, `passlib`, `starlette`), que no se actualizan antes de la
entrega por la misma razón que los pines de Python 3.13. Test nuevo:
`models.utcnow()` es UTC y sin zona.

**Error encontrado: `--backend-python` con ruta relativa**
(`scripts/capturas_demo.py`, `prueba_interna.py`, `prueba_red.py`). Los
tres scripts lanzan el backend con `cwd=backend/`, y en POSIX una ruta
relativa del ejecutable se resuelve contra ese `cwd`: el comando que
documentan los README y el checklist de pasaje
(`--backend-python backend/.venv/bin/python`, corrido desde `mvp/`) fallaba
con `FileNotFoundError`. Se agregó `resolve_python` en `capturas_demo.py`
(la usan los tres): convierte una ruta en absoluta y deja igual un nombre
de comando como `python3`. Verificado corriendo los tres scripts con la
ruta relativa.

**`index.html`:** se quitó la referencia a `/favicon.svg`, que no estaba en
el proyecto (hallazgo Baja del Revisor); el navegador usa su ícono por
defecto.

**Prueba:**
- `pytest` → **56 passed** (55 + el de `utcnow`), 53 avisos de terceros.
- `npm test` → 6/6; `npm run build` OK (294 kB de JS, igual que antes).
- `scripts/evaluar.py` antes y después de M5: salidas idénticas byte a
  byte (ver M5).
- `prueba_interna.py` (corrida 3): 12/12 conformes, ≈ 9,3 min.
- Regresión final sobre el código ya con B11 y la corrección de rutas,
  usando la ruta relativa del checklist: `capturas_demo.py` 15/15
  capturas (se revisó la 11: percentil y factores en palabras, horas en
  hora argentina); `prueba_red.py` 3/3 conformes (intentos a 5,0 / 11,7 /
  21,5 / 43,4 s; 80/80 pulsaciones; buffer 20 039 + 5 001; reconexión en
  0,1 s). Los resultados vigentes de `prueba_red_resultados.md` (13/10) no
  se reemplazaron: esta corrida solo confirma que el comportamiento se
  mantiene; los intervalos difieren dentro de la banda de ±20 % por la
  variación aleatoria del *backoff*.
- Diagramas compilados y revisados (ver M7).

**Qué quedó pendiente:** nada de lo asignado al desarrollo. Los avisos de
deprecación de terceros desaparecen al actualizar `python-jose`/`passlib`,
lo que conviene hacer junto con los pines de Python 3.13.

---

## Incremento 12 — Reorientación: panorama de la evaluación, reglas del examen y reencuadre del modelo (15/10)

**Por qué.** Reorientación aprobada el 14/10 (`equipo/REORIENTACION.md`, tareas R1–R3): ImprontIA como plataforma de **trazabilidad e inteligencia del proceso de evaluación digital**. Hace visible el proceso, interpreta los eventos según las reglas del examen y le da al docente un panorama agregado, útil aunque nadie haya hecho trampa. Atipicidad estadística no es fraude.

**Restricciones respetadas.** Sin cambio de esquema (ninguna columna ni tabla nueva), sin tocar el pipeline de métricas ni el cálculo del Isolation Forest, y con el comportamiento por defecto idéntico.

### R1 — Panorama de la evaluación
- `GET /exams/{id}/panorama` (solo el docente dueño; 404 si no es suya). Lee únicamente `Metric` (sesión completa, `item_ref = None`) e `Indicator` ya guardados de las sesiones **finalizadas**; no recalcula nada.
- Devuelve:
  - `n_sesiones` y `sesiones_requieren_revision`;
  - mediana y p25–p75 de `session_duration_ms`, `idle_ratio`, `paste_chars_total`, `tab_switch_count` y `focus_loss_duration_total_ms`;
  - sesiones por tipo de indicador (y cuántas fueron "permitidas por las reglas");
  - % de sesiones marcadas por el modelo y conteo de las métricas más frecuentes en sus explicaciones (`top_features`).
- Cálculo en una función pura, `app/processing/panorama.py::compute_panorama` (percentiles con `numpy.percentile`, interpolación lineal).
- Dashboard: pestañas "Sesiones | Panorama" en el detalle de la evaluación (`SessionsList.tsx` + `PanoramaView.tsx` nuevo): tarjetas, tabla de medianas y barras en CSS, sin librerías nuevas.

### R2 — Eventos según las reglas del examen
- Dos reglas por política: `permite_pegado` y `permite_otras_pestanas` (default `false`).
- **Sin migración:** se guardan como entradas reservadas (`"regla:permite_pegado"`, `"regla:permite_otras_pestanas"`) dentro del mismo JSON `PolicyCapture.allowed_signals`. La API las expone como booleanos (`ExamCreate`, `PolicyUpdate`, `PolicyOut`) y las quita de la lista de señales que reciben el estudiante (`/exams/{code}/info`, `/sessions/start`) y el dashboard. Lógica en `app/processing/rules.py`.
- Si la regla está activa, `paste_volume_alto` (pegado) o `cambios_pestana_frecuentes` y `perdida_foco_prolongada` (pestañas) **se siguen generando** (trazabilidad), con nivel **bajo**, la aclaración "Esto está permitido por las reglas de esta evaluación", `explanation.permitido_por_reglas = true` y **sin priorizar** la sesión.
- Se aplica al finalizar la sesión con la versión de política que aceptó el estudiante (RNF04). El modelo poblacional no cambia: puede seguir marcando la sesión por su cuenta.
- `evaluate_session(features, pop_model, rules=None)`: el parámetro nuevo es opcional; sin reglas el resultado es el de antes. `scripts/evaluar.py` no lo usa.
- Dashboard: dos casillas "Reglas del examen" al crear la evaluación (`ExamsList.tsx`) y al editar la política (`PolicyCard.tsx`, crea versión nueva); la política muestra "Permitido por las reglas". En el detalle, un indicador permitido se muestra con el estilo informativo.

### R3 — Reencuadre del indicador del modelo (solo textos)
- `format.ts`: `atipico_modelo_poblacional` se lee "Proceso de interacción distinto al de la cohorte".
- Detalle de sesión y panorama: aclaración fija "Indica dónde mirar, no una conducta indebida."
- El `kind`, la descripción guardada por el backend y el cálculo no cambian.

### Verificación
- `pytest`: **63 passed** (56 anteriores + 7 nuevos en `tests/test_incremento12.py`), 61 warnings (todos de terceros: jose, passlib, starlette).
- `npm test`: **10/10** (6 anteriores + 4 nuevos en `tests/format.test.ts`). `npm run build` OK (301 kB). `npx oxlint src tests` sin hallazgos.
- **Protocolo sintético por defecto (20 repeticiones)**, antes y después del cambio: `resultados_sinteticos.json`, `sesiones_sinteticas.csv` y `roc_modelo.csv` **idénticos byte a byte**. Pipeline FAR 3,6 % / FRR 11,7 %; modelo AUC 0,669, EER 0,390, AP 0,704: los mismos de `docs/evaluacion/resultados_sinteticos.md`. También idéntica la corrida corta de 3 repeticiones.
- Revisión visual con backend + dashboard reales (27 sesiones sintéticas de `seed_demo.py` + 1 con 850 caracteres pegados en una evaluación con `permite_pegado`): panorama con 28 sesiones, 4 marcadas por el modelo (14 %), pegado "1 permitido por las reglas"; en el detalle, el pegado aparece con nivel bajo y la aclaración, y el indicador del modelo con el texto nuevo.

---

## Incremento 13 — Fase 2, P01: despliegue accesible (PostgreSQL real, modo producción y guía de Render) (15/10)

**Por qué.** Fase 2 (`equipo/TABLERO.md`): Martina y Juan tienen que poder simular exámenes desde dos computadoras. Hasta ahora el MVP solo se había corrido con SQLite y `docker-compose.yml` nunca se había probado; además el backend arrancaba con el secreto JWT de desarrollo si nadie fijaba otro, y el CORS estaba fijo en `localhost:5173`.

**Restricciones respetadas.** Sin cambio de esquema, pipeline ni Isolation Forest. Sin variables de entorno el backend se comporta exactamente como antes (mismo secreto de desarrollo, SQLite, CORS a `localhost:5173`).

### Qué se construyó
- `app/config.py` (nuevo): configuración por entorno, en funciones puras.
  - `IMPRONTIA_ENV=production` activa las validaciones. El backend **no arranca** sin un `JWT_SECRET` propio de al menos 32 caracteres; rechaza el de desarrollo y los `change-me…`.
  - `DATABASE_URL` acepta `postgres://…` / `postgresql://…` (el formato de Render, Railway y Neon) y lo normaliza a `postgresql+psycopg2://…`.
  - `CORS_ORIGINS`: lista separada por coma. Default: `http://localhost:5173`.
  - `SEED_TEACHERS` (`mail:clave,mail:clave`): crea los docentes al arrancar si no existen. Pensado para servicios gratuitos sin consola. Nunca cambia la clave de uno existente.
- `database.py`: usa `config.database_url()`; con PostgreSQL, `pool_pre_ping=True` (las bases gestionadas cortan conexiones inactivas). `auth.py`: el secreto sale de `config.jwt_secret()`. `main.py`: CORS desde `CORS_ORIGINS` y alta de `SEED_TEACHERS`.
- `backend/Dockerfile`: Python 3.12 (la versión de los tests; antes 3.11), puerto desde `PORT` y `--proxy-headers` (HTTPS terminado en el proxy del hosting).
- `docker-compose.yml`:
  - backend en modo producción, con `JWT_SECRET` obligatorio (`${JWT_SECRET:?…}`, Compose no levanta sin él) y healthcheck propio;
  - clave de la base, `CORS_ORIGINS`, `SEED_TEACHERS` y URL pública de la API tomadas de `.env`;
  - el puerto de PostgreSQL ya no se publica al host;
  - Metabase pasa a perfil opcional (`--profile metabase`);
  - `restart: unless-stopped`.
- `mvp/env.example` (en el repo: `mvp/.env.example`): plantilla del `.env`.
- `mvp/render.yaml`: Blueprint de Render (base PostgreSQL gratuita + API Docker + dashboard estático con reescritura de SPA); `JWT_SECRET` lo genera Render. En el repo va en la raíz.
- `scripts/verificar_despliegue.py` (nuevo): verificación de humo por HTTP contra cualquier despliegue. Recorre:
  - salud, login (bueno, clave mala y token falso);
  - evaluación, info pública y sesión con 81 eventos, con reintento idempotente;
  - cierre con pipeline, detalle con indicador y panorama;
  - CORS del dashboard (permitido) y de un origen ajeno (rechazado).
- `docs/despliegue.md` (nuevo): guía con las variables, el camino A (Docker Compose, incluida la red local) y el camino B (Render, con los límites del plan gratuito), qué se verificó y seguridad mínima.
- `tests/conftest.py`: con `TEST_DATABASE_URL` la misma suite corre contra otra base (recrea las tablas en cada corrida). Sin la variable, SQLite temporal como siempre.

### Verificación
- **Línea de base** (antes de tocar nada): `pytest` 63 passed; protocolo sintético por defecto (20 repeticiones) FAR 3,6 % / FRR 11,7 %, AUC 0,669, EER 0,390, AP 0,704.
- `pytest`: **75 passed** (63 + 12 en `tests/test_despliegue.py`), 61 avisos de terceros. Los 12 cubren:
  - normalización de URL;
  - secreto de desarrollo fuera de producción;
  - 5 casos de secreto inválido en producción;
  - secreto válido;
  - CORS;
  - formato de `SEED_TEACHERS`;
  - alta idempotente sin cambiar claves;
  - el backend no arranca en producción sin secreto (subproceso real).
- **Suite completa sobre PostgreSQL 16.15** (columnas JSONB reales): **75 passed** con `TEST_DATABASE_URL`. Se confirmó en la base que quedaron las filas (44 sesiones, 3 557 eventos).
- **Backend en modo producción contra PostgreSQL**, con el comando del contenedor (`uvicorn … --port $PORT --proxy-headers`), `DATABASE_URL` en formato `postgres://`, dos docentes en `SEED_TEACHERS` y el CORS de Render:
  - `verificar_despliegue.py`: **14/14** con cada docente.
  - Sin `JWT_SECRET`, no arranca.
  - Reiniciado con otro secreto: datos persistentes, el seed no duplica ni cambia claves (12/12; sin chequeos de CORS en esa pasada).
- **Protocolo sintético por defecto, después del cambio:** `resultados_sinteticos.json`, `sesiones_sinteticas.csv` y `roc_modelo.csv` **idénticos byte a byte** a la línea base.
- `docker compose config` valida el archivo y falla con mensaje claro si falta `JWT_SECRET`. `render.yaml` parsea como YAML válido.
- **No verificado:**
  - Levantar los contenedores: el entorno de la sesión tiene el demonio de Docker, pero no puede bajar imágenes de Docker Hub (403 del proxy).
  - Crear los servicios en Render: requiere la cuenta de Martina.
  - En los dos casos, `verificar_despliegue.py` es la comprobación a correr la primera vez.
- El dashboard no se tocó.

---

## Incremento 14 — Fase 2, P02: migraciones con Alembic y campos del ER que faltaban (16/10)

**Por qué.** Fase 2 (`equipo/TABLERO.md`, P02): en cuanto haya datos reales (simulaciones de Martina y Juan), cualquier cambio de esquema necesita migraciones; recrear la base deja de ser una opción. Además, el cap. 15 especifica tres campos del modelo entidad-relación que el código no tenía (cap. 17 §Limitaciones): `politica_captura.retencion_dias`, `metrica.evento_desde/evento_hasta` e `indicador.estado`.

**Restricciones respetadas.** Sin cambios en el pipeline, las reglas ni el Isolation Forest: ninguno lee los campos nuevos. Los campos nuevos son opcionales en la API y, sin usarlos, las respuestas son las de antes más tres claves nuevas.

### Qué se construyó
- **Alembic** (`alembic==1.13.3` en `requirements.txt`):
  - `backend/alembic.ini` y `backend/migrations/` (`env.py`, plantilla y `versions/`). La carpeta se llama `migrations` y no `alembic` para no tapar el paquete `alembic` al correr desde `backend/`.
  - `env.py` toma la URL de `DATABASE_URL` con la misma normalización que el backend (`postgres://` → `postgresql+psycopg2://`), usa `render_as_batch=True` (SQLite no tiene `ALTER/DROP COLUMN`) y no toca el logging (no pisa el de uvicorn).
  - **`0001_esquema_inicial`**: reproduce tabla por tabla el esquema que creaba `create_all` hasta el Incremento 13, incluidos los tipos `ENUM` de PostgreSQL, índices y restricciones.
  - **`0002_campos_er`**: agrega `policy_captures.retencion_dias` (entero, nulo), `metrics.evento_desde` / `metrics.evento_hasta` (enteros, nulos) e `indicators.estado` (texto, no nulo, `server_default 'pendiente'`). Los indicadores existentes que ya citaba una revisión pasan a `'atendido'`. Tiene `downgrade`.
- **`app/db_migrations.py`** (nuevo) y `main.py`: el backend ya no llama a `Base.metadata.create_all`; al arrancar aplica `upgrade head`.
  - Base vacía: aplica todas las migraciones.
  - Base creada antes de P02 (tiene `users` pero no `alembic_version`): la marca (`stamp`) en `0001` y aplica las siguientes, **sin tocar los datos**.
  - Base ya migrada: aplica solo lo pendiente; si no hay nada, no hace nada.
  - Por línea de comandos, desde `backend/`: `alembic upgrade head`, `alembic current`, `alembic revision --autogenerate -m "…"`.
- **Campos nuevos** (`models.py`, `schemas.py`, routers):
  - `PolicyCapture.retencion_dias`: opcional en `POST /exams` y `POST /exams/{id}/policy`, entre 1 y 365 días (422 fuera de rango); `PolicyOut` lo devuelve. `null` = sin plazo definido (todas las políticas anteriores). Cada versión de la política declara el suyo. **Solo se guarda**: la purga periódica (RNF10) queda para otra tarea.
  - `Metric.evento_desde` / `evento_hasta`: primer y último `Event.seq` de los eventos sobre los que se calculó la métrica. Para la sesión completa, el rango de todos sus eventos; para el desglose por ítem, el de los eventos de ese ítem. `null` si la sesión no tuvo eventos o si la métrica es anterior a la migración. `MetricOut` los devuelve.
  - `Indicator.estado`: `"pendiente"` al crearse; pasa a `"atendido"` cuando una revisión lo cita en `indicator_ids`. No es un veredicto: la decisión sigue viviendo solo en `Review`. `IndicatorOut` lo devuelve.
- `Dockerfile`: copia `alembic.ini` y `migrations/`. `tests/conftest.py`: con `TEST_DATABASE_URL` también borra `alembic_version`, para que la base de prueba se recree con las migraciones.

### Verificación
- **Línea de base** (antes de tocar nada): `pytest` **75 passed** en SQLite y **75 passed** en PostgreSQL 16.15; protocolo sintético por defecto (20 repeticiones) FAR 3,6 % / FRR 11,7 %, AUC 0,669, EER 0,390, AP 0,704.
- **La migración inicial es el esquema anterior:** una base creada con `create_all` (código del Incremento 13) y otra creada con `upgrade 0001` dan el mismo esquema: `pg_dump -s` idéntico en PostgreSQL (0 líneas de diferencia) y el mismo `sqlite_master` en SQLite.
- **Una base vieja migrada queda igual que una nueva:** la base de PostgreSQL creada con `create_all` llevada a `head` (`stamp+upgrade`) y una vacía llevada a `head` tienen `pg_dump -s` idéntico; lo mismo en SQLite.
- **Modelos y migraciones coinciden:** `alembic check` → "No new upgrade operations detected", y un test compara `models.py` con la base migrada (`compare_metadata` vacío) en SQLite y en PostgreSQL.
- `pytest`: **81 passed** (75 + 6 en `tests/test_migraciones.py`) en SQLite y **81 passed** en PostgreSQL 16.15; 76 avisos, todos de terceros (jose, passlib, starlette). Los 6 cubren:
  - base de la suite en `head` y sin diferencias con los modelos;
  - `upgrade` → `downgrade` a `0001` → `upgrade` sobre una base vacía, e idempotencia;
  - base anterior a P02 con datos: se marca, se actualiza y conserva usuarios, métricas e indicadores (el citado por una revisión queda `atendido`, el otro `pendiente`);
  - `retencion_dias` opcional, 90 y 365 válidos, 0 / 366 / −5 → 422;
  - rangos de eventos por sesión e ítem (`(0, 4)`, `q1 (0, 1)`, `q2 (2, 4)` con dos lotes) y `estado` que pasa a `atendido` solo con una revisión que cita el indicador;
  - sesión sin eventos: métricas con rango nulo.
- **Backend en modo producción contra PostgreSQL** (`IMPRONTIA_ENV=production`, URL `postgres://`, `SEED_TEACHERS`): arranca, crea el esquema por migraciones (`alembic_version = 0002_campos_er`), `/health` y login OK.
- **Protocolo sintético por defecto (20 repeticiones), antes y después:** mismas cifras (FAR 3,6 % / FRR 11,7 %, AUC 0,669, EER 0,390, AP 0,704) y mismo hash SHA-256 de los 1 600 registros por sesión y de las métricas agregadas. Corrido con `run_experiment(ExperimentConfig())`, la misma función y configuración que usa `scripts/evaluar.py` por defecto.
- El dashboard no se tocó (los campos nuevos todavía no se muestran).

---

## Incremento 15 — Fase 2, P03: kit de simulación (etiqueta oculta, exportación y análisis de sesiones reales) (17/10)

**Por qué.** Fase 2 (`equipo/TABLERO.md`): Martina y Juan van a rendir simulaciones de examen para obtener las primeras sesiones humanas etiquetadas. Para eso hacía falta (1) declarar la condición simulada de cada sesión sin que el docente la vea, (2) sacar esas sesiones de la base sin datos personales y (3) correr sobre ellas el mismo procedimiento de evaluación del Incremento 6.

**Restricciones respetadas.** El pipeline, las reglas y el Isolation Forest no cambian y no leen la etiqueta. Sin etiqueta, una sesión se procesa exactamente igual que antes. El protocolo sintético por defecto da los mismos archivos byte a byte.

### Qué se construyó
- **Etiqueta de condición** (`sessions.condicion_simulacion`, migración `0003_condicion_simulacion`, con `downgrade`). Valores: `normal`, `pegado`, `transcripcion`, `consulta_externa` y `suplantacion` (`app/simulacion.py`). NULL en toda sesión real.
  - Entra por `POST /sessions/start` como campo opcional `condicion_simulacion`. Un valor desconocido da 422.
  - No está en ningún esquema de salida: el docente no la ve en el listado, el detalle ni el panorama. No va en `context`, porque `context` sí se devuelve en el detalle.
- **Dashboard:** con `?simulacion=1` en el enlace de rendición, la vista del estudiante muestra el selector "Condición de esta simulación", que es obligatorio en ese modo. Sin el parámetro no aparece y nunca se envía una condición (`format.ts`: `isSimulationMode`, `simulationConditionToSend`).
- **`app/evaluation/reales.py`** (funciones puras):
  - `registros_desde_sesiones`: filas del CSV. Usa alias `S001`/`E01`/`P01` y no incluye códigos, fechas, contexto, eventos crudos ni revisiones. `marcada_reglas` no cuenta un indicador permitido por las reglas del examen (nivel bajo, R2).
  - `analizar`:
    - **operación**: FAR y FRR de `needs_review` contra la etiqueta;
    - **modelo fuera de línea**: IF entrenado solo con sesiones `normal` y sin la sesión evaluada. Con `excluir_participante`, además sin ninguna sesión de la misma persona;
    - AUC-ROC, AP y EER globales y por condición;
    - intervalos 95 % remuestreando participantes;
    - avisos (menos de 21 normales, menos de 5 participantes, sesiones sin score).
  - Usa `metrics.py` (`far_frr`, `score_metrics`) y `fit_population_model` / `score_with_model` sin cambios.
- **`scripts/exportar_sesiones.py`**: lee la base de `DATABASE_URL` (la etiqueta no sale por la API). Opciones `--evaluacion CÓDIGO` (repetible), `--salida` e `--incluir-sin-etiqueta`.
- **`scripts/analizar_reales.py`**: imprime el reporte. Con `--salida DIR` guarda `resultados_simulaciones.md` y `.json`. Opciones `--excluir-participante`, `--bootstrap` y `--semilla`.
- **`docs/simulaciones/protocolo.md`**: preparación, condiciones, volumen y orden contrabalanceado, planilla de campo, comandos de exportación y análisis, cómo informar y privacidad.

### Decisiones (baratas de cambiar)
1. La etiqueta se declara al iniciar y no se puede corregir desde la interfaz. Una sesión mal etiquetada se marca como inválida en la planilla y se saca del CSV.
2. El AUC/AP/EER se calcula fuera de línea (dejar una sesión afuera), no con el score guardado. El backend solo guarda el score del IF cuando marca la sesión, y en operación las primeras sesiones no tienen modelo.
3. La condición es un texto validado por la API y no un enum de la base. Así, agregar una condición no requiere migración.

### Verificación
- `pytest`: **88 passed** (81 + 7 de `tests/test_simulaciones.py`) en SQLite y **88 passed** en PostgreSQL 16, con 84 avisos de terceros.
- `npm test`: **13/13** (10 + 3 de `tests/simulacion.test.ts`). `npm run build` OK (302,6 kB).
- **Protocolo sintético por defecto (20 repeticiones), antes y después:** `resultados_sinteticos.json`, `sesiones_sinteticas.csv`, `roc_modelo.csv` y `barrido_dificultad.csv` idénticos byte a byte. Pipeline FAR 3,6 % / FRR 11,7 %; modelo AUC 0,669, EER 0,390, AP 0,704.
- `exportar_sesiones.py` y `analizar_reales.py` corridos por línea de comandos contra la base PostgreSQL de la suite: 47 sesiones exportadas, 3 con condición. El reporte sale con los avisos de población insuficiente y de pocos participantes.
- Prueba del análisis con sesiones **sintéticas** etiquetadas como simulaciones (30 normales y 6 por condición, 2 "participantes"; no son resultados):
  - las reglas detectan 6/6 de `pegado`, `transcripcion` y `consulta_externa`;
  - el modelo fuera de línea separa `suplantacion` (perfil `ritmo_distinto`, 2σ) con AUC 0,894;
  - en las otras tres condiciones el AUC del modelo queda entre 0,36 y 0,71. Es coherente con el Incremento 6: esas condiciones las detectan las reglas.

---

## Qué queda pendiente (a propósito, no por descuido)

- **Levantar los contenedores de `docker-compose.yml`.** Desde el
  Incremento 13 el backend está probado contra PostgreSQL real (suite
  completa y modo producción) y el archivo de Compose se valida con
  `docker compose config`, pero los contenedores no se pudieron levantar en
  la sesión (sin acceso a Docker Hub). La primera vez, correr
  `docker compose up --build -d` y `scripts/verificar_despliegue.py`
  (ver `docs/despliegue.md`).
- **Purga por `retencion_dias` (RNF10).** Desde el Incremento 14 la política
  guarda el plazo (1–365 días, opcional), pero nada borra todavía eventos ni
  métricas vencidos; tampoco hay eliminación de cuenta ni de sesión (RF17).
- **Mostrar los campos nuevos en el dashboard** (Incremento 14): plazo de
  retención en la política, rango de eventos de cada métrica y estado
  "atendido" del indicador. Hoy solo los devuelve la API.
- **Calibración real del Isolation Forest y de los umbrales.**
  `MIN_SESSIONS_FOR_MODEL = 20` es el mínimo técnico para que el algoritmo
  funcione (ver Incremento 5) y los umbrales de `indicators.py` (incluido
  el corte de nivel alto por percentil, 5 %) siguen siendo placeholders; la
  evaluación del Incremento 6 usa datos sintéticos. Calibrar y medir
  desempeño real depende de sesiones piloto (cap. 18).
- **Regla de ritmo uniforme robusta** (Incremento 9): reemplazar el desvío
  estándar de la duración de pulsación por una medida robusta (rango
  intercuartílico o MAD) y calibrar el umbral con la latencia real de la
  captura en distintos equipos; una sola pulsación atípica hoy alcanza para
  que un tecleo automatizado escape a la regla.
- **Tiempo entre teclas sin pausas fuera de foco** (Incremento 9): excluir
  del `mean_flight_time_ms` los intervalos que contienen una pérdida de
  foco; y evaluar si `window_blur` (cambio a otra aplicación con el
  navegador visible, que hoy se registra pero no se usa) debería alimentar
  un indicador de atención.
- **Pines de dependencias para Python 3.13** (ver "Línea de base"): hoy
  hay que usar 3.11/3.12. No se actualizaron a propósito antes de la
  entrega: cambiar de versión de scikit-learn/numpy podría mover los
  resultados del Incremento 6 ya citados en el documento. Al hacerlo,
  actualizar también `python-jose` y `passlib`, origen de los avisos de
  deprecación que quedan en `pytest` (Incremento 11).
- **Buffer de la captura persistente** (Incremento 10): hoy vive en memoria;
  si el estudiante cierra la pestaña sin conexión, lo pendiente se pierde.
- **La superficie de respuesta es un textarea simple.** Suficiente para que
  el MVP capture señales reales sobre una respuesta real, pero está lejos
  de un editor de examen completo — a propósito, cap. 13 excluye
  explícitamente que ImprontIA sea "un LMS ni un editor completo de
  evaluaciones". Si el examen real vive en otra plataforma (Moodle, Forms),
  este mecanismo concreto de asociación queda abierto, tal como el propio
  capítulo 13 lo señala.
- Docentes se crean hoy con un script (`scripts/seed_teacher.py`) o, desde
  el Incremento 13, con `SEED_TEACHERS` al arrancar; no hay todavía una
  pantalla de alta de cuentas — razonable para un MVP de una sola
  institución/tesis, no para producción multi-institución.
- `oxlint` sin argumentos recorre `node_modules`; usar `npx oxlint src tests`
  (o agregar un `.oxlintrc` que lo ignore).

**Resueltos desde la versión anterior de esta lista:** UI para versionar
la política de un examen (Incremento 8); vista de "sesiones con validación
adicional pendiente" para RF11/HU08 (Incremento 8); los eventos de teclado
ya no identifican la tecla, una política sin señales ya no captura nada y la
vista del estudiante pide un código seudónimo en vez del legajo
(Incremento 9); backoff exponencial, buffer acotado y registro de buffer
agotado / falla persistente en la sincronización, nivel del indicador del
modelo por percentiles, score crudo fuera del dashboard y declaración
precisa de la lectura del portapapeles (Incremento 10); prueba interna
repetida sobre el código entregado, generador sintético sin código de
tecla, diagramas fieles a quién persiste, fechas sin la API deprecada y
scripts de prueba que aceptan rutas relativas (Incremento 11); backend
probado contra PostgreSQL real, `JWT_SECRET` obligatorio en producción,
CORS configurable y guía de despliegue (Incremento 13); migraciones con
Alembic (adiós a `create_all`) y las columnas del ER que faltaban:
`retencion_dias`, `evento_desde/evento_hasta` e `Indicator.estado`
(Incremento 14). Con esto no quedan desvíos abiertos respecto de lo que
especifica el cap. 15 para la captura, el modelo de datos y la salida del
modelo; lo pendiente son decisiones de alcance y calibración.
