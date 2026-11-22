# Prueba interna end-to-end del MVP (T18 · Incremento 9, repetida sobre el código final)

> **Qué es y qué no es.** Es una verificación de **funcionamiento** del
> sistema real, de punta a punta, con escenarios guionados ejecutados por
> automatización (Playwright/Chromium) sobre el backend y el dashboard
> reales. **No** es un piloto ni mide desempeño de detección: los escenarios
> los escribió el equipo sabiendo cómo funcionan las reglas y no hay
> participantes humanos (D03). Lo que sí muestra es que, ante cada
> comportamiento guionado, la cadena completa —captura en el navegador →
> envío por lotes → persistencia → métricas → indicadores → vista docente—
> produce lo esperado, y dónde no lo hace.

- Script: `mvp/scripts/prueba_interna.py` (reproducible; ver README).
- Resultados generados (tablas completas, no editar a mano):
  - **Corrida 3 (vigente, código entregado: Incremento 10 + revisión del
    14/10):** [`prueba_interna_resultados.md`](prueba_interna_resultados.md),
    [`prueba_interna.csv`](prueba_interna.csv).
  - Corrida 2 (código del Incremento 9, sin código de tecla):
    [`prueba_interna_corrida2_resultados.md`](prueba_interna_corrida2_resultados.md),
    [`prueba_interna_corrida2.csv`](prueba_interna_corrida2.csv).
  - Corrida 1 (antes de quitar el código de tecla de la captura):
    [`prueba_interna_corrida1_resultados.md`](prueba_interna_corrida1_resultados.md),
    [`prueba_interna_corrida1.csv`](prueba_interna_corrida1.csv).
  - `prueba_interna.json` (detalle con *z-scores*) se regenera y no se versiona.
- Repetición manual (≈ 15 min): [`protocolo_prueba_manual.md`](protocolo_prueba_manual.md).
- Corridas 1 y 2 del 12/10/2026 y corrida 3 del 14/10/2026: 4 escenarios ×
  3 repeticiones = 12 sesiones por corrida, ≈ 9,5 min cada una; Chromium 141
  *headless*; backend con SQLite temporal. Guion, semillas y línea base son
  idénticos en las tres. Entre la corrida 1 y la 2 se cambió **solo** la
  captura de teclado (`capture.ts` dejó de enviar qué tecla se pulsó,
  Incremento 9). Entre la 2 y la 3 se incorporó el Incremento 10 (cola de
  sincronización con *backoff* y buffer acotado en `syncQueue.ts`, lista de
  señales antes del consentimiento, lectura del portapapeles solo si está
  habilitado, nivel del indicador del modelo por percentil); la corrida 3
  es la que corresponde al código entregado (hallazgo A9 de la revisión
  del 13/10).

## 1. Procedimiento

Para **cada escenario y repetición** el script:

1. Crea una evaluación nueva por la API (todas las señales habilitadas) y le
   carga una **línea base de 24 sesiones sintéticas normales** por la API
   real (`scripts/seed_demo.py`, semilla fija 7, la misma en todas), para que
   el Isolation Forest tenga población (mínimo 20).
2. Abre la vista del estudiante del dashboard (`/exam/<código>`) en un
   contexto de navegador sin credenciales docentes, completa el código de
   participante, tilda el consentimiento, comienza, ejecuta el guion y
   pulsa **Finalizar y entregar**. La captura la hace `capture.ts`; los
   eventos viajan en lotes cada 5 s como en uso real (desde el Incremento 10,
   a través de `syncQueue.ts`); el procesamiento corre en
   `POST /sessions/{id}/end`.
3. Del lado docente verifica: (a) indicadores devueltos por la API frente a
   los esperados; (b) que la vista **Detalle de sesión** del dashboard
   muestre la misma cantidad de indicadores y el mismo estado ("Requiere
   revisión" / "Sin indicadores"); (c) que **ningún evento guardado en la
   base contenga texto** de la respuesta ni del bloque pegado (solo claves
   de metadatos permitidas, RNF01) y, desde la corrida 2, que **los eventos
   de teclado no identifiquen la tecla** pulsada.

| Escenario | Guion | Indicador de regla esperado |
|---|---|---|
| `normal` | Mouse + tecleo de la respuesta (129 caracteres) con ritmo variable: pulsación 60–130 ms y 70–220 ms entre teclas; una salida de pestaña de ≈ 2 s. | Ninguno |
| `pegado_masivo` | Tecleo de una frase corta y pegado de un bloque de 461 caracteres (evento `paste` real del DOM). | `paste_volume_alto` (umbral 200) |
| `cambios_foco` | Tecleo con ritmo variable intercalado con 7 salidas de pestaña de 1,5–3 s. | `cambios_pestana_frecuentes` (umbral 5) |
| `transcripcion` | Tecleo a ritmo constante: pulsación fija de 80 ms y 110 ms entre teclas (como el de un texto inyectado o transcripto mecánicamente). | `ritmo_tecleo_atipico` (desvío de pulsación < 5 ms) |

## 2. Resultados

| Escenario | Conformes¹ (corrida 1 / 2 / 3) | Indicador del modelo (IF) | Dashboard = API | Sin texto en eventos |
|---|---|---|---|---|
| `normal` | 3/3 · 3/3 · 3/3 | 0/9 | 9/9 | 9/9 |
| `pegado_masivo` | 3/3 · 3/3 · 3/3 | 0/9 | 9/9 | 9/9 |
| `cambios_foco` | 3/3 · 3/3 · 3/3 | 0/9 | 9/9 | 9/9 |
| `transcripcion` | **2/3** · 3/3 · 3/3 | 0/9 | 9/9 | 9/9 |
| **Total** | **11/12 · 12/12 · 12/12 (35/36)** | 0/36 | 36/36 | 36/36 |

¹ *Conforme* = se generaron todos los indicadores de regla esperados y
ningún otro indicador de regla.

Valores observados (detalle por sesión en los archivos de resultados):

- `normal`: ninguna regla disparada; 1 cambio de pestaña (umbral 5);
  pulsación media 101–105 ms, desvío 18–21 ms.
- `pegado_masivo`: `paste_chars_total` = 461 en las nueve sesiones (el
  sistema registró la **longitud** exacta del bloque y no su contenido).
- `cambios_foco`: `tab_switch_count` = 7 y 15–16 s fuera de foco en las
  nueve; no se disparó `perdida_foco_prolongada` (umbral 60 s), como
  corresponde al guion.
- `transcripcion`: desvío de pulsación de 1,3 a 2,4 ms en siete sesiones;
  **9,1 ms** en la corrida 1, repetición 1 (regla **no** disparada) y
  **4,9 ms** en la corrida 2, repetición 1 (regla disparada por 0,1 ms). En
  la corrida 3 no hubo pulsaciones demoradas: 1,3 / 2,1 / 2,4 ms.
- Corridas 2 y 3: ningún evento de teclado guardado contiene `code` ni
  `key`; los indicadores obtenidos coinciden con los de la corrida 1 y las
  métricas de teclado difieren en menos de 1,5 ms de media entre corridas
  (ruido de temporización), lo que es consistente con que ni quitar el
  código de tecla ni el Incremento 10 alteran el cálculo de tiempos de
  pulsación (además verificado con pruebas unitarias).
- Corrida 3: la cola de sincronización nueva no introdujo pérdidas ni
  avisos: ninguna sesión registró `captura_incompleta` (sin cortes de red,
  no corresponde) y el número de eventos por escenario es idéntico al de
  las corridas anteriores (301 / 122 / 325 / 297).

## 3. Interpretación y decisiones

**3.1 La cadena funciona de punta a punta.** En las 36 sesiones los eventos
capturados en el navegador llegaron al backend, se procesaron al finalizar,
y lo que muestra el dashboard docente coincide con lo que devuelve la API.
Los tres escenarios basados en señales discretas (pegado, pestañas, sesión
normal) dieron el resultado esperado en 27/27. La corrida 3 confirma que el
código entregado (Incremento 10) conserva ese comportamiento: 12/12.

**3.2 Privacidad verificada sobre la base real.** En las 36 sesiones, los
eventos persistidos contienen solo instantes, coordenadas, estados de
visibilidad y cantidades de caracteres; ninguna palabra de la respuesta ni
del bloque pegado: **el texto no se envía ni se guarda**. La corrida 1
detectó además que cada pulsación se guardaba con su código de tecla física
(`code`), de cuya secuencia se podría reconstruir aproximadamente lo
tecleado (observación también registrada en el cap. 17, §Limitaciones).
**Decisión:** la captura dejó de enviar qué tecla se pulsó (Incremento 9);
las corridas 2 y 3 verifican que ya no se guarda y que las métricas no
cambian.

**3.3 Hallazgo: la regla de ritmo uniforme es frágil ante una sola
pulsación atípica.** En las dos sesiones `transcripcion` problemáticas,
128 de 129 pulsaciones midieron entre 85 y 93 ms, pero **una** midió 189 ms
(corrida 1) o 141 ms (corrida 2), por una demora puntual de la cadena de
automatización/navegador. Esa sola pulsación llevó el desvío estándar de
≈ 1,5 ms a 9,1 ms (la sesión escapó a la regla) y a 4,9 ms (la regla se
disparó por 0,1 ms). En la corrida 3 no se produjo ninguna demora y las
tres sesiones quedaron claramente por debajo del umbral, lo que confirma que
el resultado depende de un evento aislado y no del guion. Además, todas las
pulsaciones se midieron ≈ 7 ms más largas que lo ordenado (87 ms frente a
80 ms): el tiempo registrado incluye la latencia de la cadena de eventos.
Consecuencias:

- El desvío estándar no es una medida robusta para esta regla: un evento
  aislado (un sobresalto, una tecla trabada, una demora del sistema) puede
  "esconder" un tecleo automatizado. **Decisión:** no se cambia la métrica
  antes de la entrega, porque un umbral nuevo cambiaría qué sesiones se
  priorizan y no hay datos de personas con los cuales calibrarlo; se
  registra como mejora prioritaria para trabajo futuro: usar una medida
  robusta de dispersión (rango intercuartílico o desviación absoluta
  mediana) y calibrar el umbral con la latencia real medida en distintos
  equipos.
- El umbral de 5 ms está en el orden del ruido de medición del propio
  navegador; confirma que los umbrales son provisorios y requieren
  calibración (cap. 15, "Decisiones técnicas que permanecen abiertas").

**3.4 El Isolation Forest no marcó ninguna sesión de navegador, ni siquiera
`transcripcion`.** Frente a su línea base, las sesiones `transcripcion` se
desvían z ≈ −4,5 en el desvío de pulsación (−3,9 a −4,7 según la sesión),
pero el modelo no las marcó. Es coherente con el hallazgo del Incremento 5:
en un Isolation Forest, un valor por **fuera** del rango observado en el
entrenamiento cae en la misma región que el valor extremo observado, de modo
que "muy por debajo del mínimo" puntúa igual que "en el mínimo"; con un
único rasgo desviado entre cinco, el puntaje no alcanza el corte del 10 %
(`contamination=0.1`). Para este patrón la **regla** es la que detecta, y el
modelo complementa en desvíos multidimensionales (perfil `ritmo_distinto`
del Incremento 6). Que `normal` no fuera marcada (0/9) es compatible con la
tasa de revisión de ≈ 10 % fijada por diseño, pero 9 sesiones no permiten
estimarla.

Dos aclaraciones para no sobreinterpretar este resultado:

- El movimiento de mouse del guion se generó **con los mismos parámetros
  que el generador sintético** (velocidad ≈ 0,6 px/ms, 100–400 ms entre
  muestras), para que la comparación con la línea base sintética fuera
  justa. En el Incremento 7 el movimiento de Playwright por defecto sí fue
  marcado (z ≈ 12 en la variabilidad de velocidad). La línea base de un
  examen real tiene que salir de sesiones reales de ese examen.
- En `cambios_foco` el tiempo medio entre teclas sube a ≈ 270 ms (z ≈ 3)
  porque las pausas fuera de la pestaña quedan dentro del intervalo
  `keyup → keydown`. Es un efecto de cómo se define la métrica; conviene
  excluir del cálculo los intervalos que contienen una pérdida de foco
  (trabajo futuro).

**3.5 Limitación de la prueba: cambio de pestaña simulado.** Playwright
mantiene la página como visible incluso con navegador visible o ventana
minimizada (se probó en esta sesión), así que el escenario `cambios_foco`
sobrescribe `document.visibilityState` y despacha el evento nativo
`visibilitychange`; el listener de `capture.ts` y todo lo que sigue son los
reales. El cambio de pestaña real lo cubre el
[protocolo manual](protocolo_prueba_manual.md), que además advierte que
cambiar de **aplicación** con Alt+Tab dejando visible el navegador solo
produce `window_blur`, que hoy no alimenta ningún indicador.

## 4. Resumen para el documento

- Técnica: prueba funcional de sistema (*end-to-end*, caja negra desde la
  interfaz del estudiante, con verificación en la API, en la interfaz
  docente y en la base de datos), complementaria de las 56 pruebas
  automatizadas unitarias y de integración del backend, de las 6 pruebas
  unitarias del frontend y de la prueba de resiliencia
  ([`prueba_red.md`](prueba_red.md)).
- Resultado: 35/36 sesiones conformes en tres corridas; la tercera, sobre
  el código entregado, 12/12. 36/36 con coincidencia dashboard–API y sin
  texto en los eventos.
- Decisiones tomadas a partir de los resultados: (1) dejar de registrar qué
  tecla se pulsa (aplicada en el Incremento 9 y verificada en las corridas
  2 y 3); (2) registrar la fragilidad de `ritmo_tecleo_atipico` y proponer
  una medida robusta de dispersión con umbral calibrado; (3) mantener las
  reglas como mecanismo principal para señales puntuales y el Isolation
  Forest como complemento para desvíos multidimensionales; (4) excluir las
  pausas por pérdida de foco del tiempo entre teclas; (5) evaluar sumar
  `window_blur` como señal de atención; (6) no introducir antes de la
  entrega cambios en las reglas o el modelo que alteren qué sesiones se
  priorizan sin una calibración con personas.
