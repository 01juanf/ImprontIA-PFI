# Evaluación del pipeline con datos sintéticos

_Generado por `scripts/evaluar.py` el 2026-10-22 22:30 UTC (scikit-learn 1.5.2, numpy 1.26.4). No editar a mano: regenerar con el script._

> **Advertencia.** Estos números provienen de sesiones **sintéticas** generadas con parámetros elegidos para ejercitar el pipeline, no calibrados con personas reales. Validan que el **procedimiento** de evaluación funciona de punta a punta (eventos → métricas → reglas + Isolation Forest → FAR/FRR/AUC/EER) y muestran cómo se comporta el pipeline frente a anomalías de forma conocida. **No son resultados del piloto ni una estimación del desempeño real** con estudiantes.

## Convención de métricas

Clase positiva = sesión anómala. **FAR** = tasa de anomalías no detectadas (FN/P). **FRR** = tasa de falsas alarmas (FP/N). **EER** = punto donde FAR = FRR. AUC-ROC, AP (average precision) y EER se calculan sobre el score continuo del Isolation Forest (`-decision_function`); las reglas son binarias y solo aportan un punto de operación. Cada celda: media ± desvío entre repeticiones [percentiles 2,5–97,5].

## Protocolo y parámetros

- Protocolo del modelo: **análisis de la cohorte al cierre** (Incremento 16, `processing/cohort.py`): la cohorte es la población más las sesiones de prueba; se entrena un único Isolation Forest con todas y cada sesión de prueba se puntúa contra ese modelo (transductivo). Prevalencia de anómalas en la cohorte: **33 %**.
- Repeticiones: **20** (semillas 2026…2045).
- Población (línea base de la evaluación): **40** sesiones, contaminación 0 % (mínimo técnico del modelo: 20).
- Prueba por repetición: **40** normales + **40** anómalas, repartidas en partes iguales entre: pegado_masivo, cambio_pestana, tecleo_automatizado, ritmo_distinto.
- Pipeline evaluado tal como está en el MVP (sin ajustar con las etiquetas): umbrales {'paste_chars_total': 200.0, 'tab_switch_count': 5.0, 'focus_loss_duration_total_ms': 60000.0, 'std_dwell_time_ms_low': 5.0}; Isolation Forest `n_estimators=200`, `contamination=0.1`, `random_state=0`.
- Población normal: dwell ~ N(95.0, 15.0) ms entre participantes, desvío intra-sesión U(15.0, 30.0); flight ~ N(160.0, 35.0) ms, intra U(40.0, 80.0); 250–500 pulsaciones; mouse ~ N(0.6, 0.15) px/ms (CV intra 0.3); cambios de pestaña ~ Poisson(0.6) con duración media 4000 ms; pegado chico con prob. 0.2 (5–60 caracteres).
- Dificultad de `ritmo_distinto`: **2.0** desvíos poblacionales en dwell, flight y velocidad de mouse.

## Resultados globales

| Componente | FAR (anomalías no detectadas) | FRR (falsas alarmas) |
|---|---|---|
| Pipeline completo (reglas ∨ modelo) | 12.4 % ± 2.4 [7.5–16.3] | 2.9 % ± 2.7 [0.0–8.8] |
| Solo reglas determinísticas | 25.0 % ± 0.0 [25.0–25.0] | 0.0 % ± 0.0 [0.0–0.0] |
| Solo Isolation Forest | 76.2 % ± 2.6 [72.5–81.3] | 2.9 % ± 2.7 [0.0–8.8] |

Score continuo del Isolation Forest (todas las anomalías vs. normales):

| AUC-ROC | AP | EER |
|---|---|---|
| 0.724 ± 0.053 [0.636–0.820] | 0.765 ± 0.062 [0.650–0.852] | 0.330 ± 0.058 [0.224–0.426] |

## Por perfil de anomalía

| Perfil | Detección pipeline | Detección reglas | Detección modelo | AUC-ROC modelo | EER modelo |
|---|---|---|---|---|---|
| `pegado_masivo` | 100.0 % ± 0.0 [100.0–100.0] | 100.0 % ± 0.0 [100.0–100.0] | 6.0 % ± 8.2 [0.0–20.0] | 0.544 ± 0.128 [0.380–0.806] | 0.461 ± 0.111 [0.248–0.600] |
| `cambio_pestana` | 100.0 % ± 0.0 [100.0–100.0] | 100.0 % ± 0.0 [100.0–100.0] | 1.5 % ± 3.7 [0.0–10.0] | 0.476 ± 0.109 [0.320–0.693] | 0.534 ± 0.101 [0.295–0.638] |
| `tecleo_automatizado` | 100.0 % ± 0.0 [100.0–100.0] | 100.0 % ± 0.0 [100.0–100.0] | 37.0 % ± 10.3 [20.0–55.2] | 0.949 ± 0.036 [0.879–0.996] | 0.098 ± 0.053 [0.025–0.200] |
| `ritmo_distinto` | 50.5 % ± 9.4 [34.8–70.0] | 0.0 % ± 0.0 [0.0–0.0] | 50.5 % ± 9.4 [34.8–70.0] | 0.926 ± 0.043 [0.849–0.988] | 0.139 ± 0.057 [0.049–0.238] |

Falsas alarmas sobre sesiones normales, por indicador:

| Indicador | Tasa sobre normales |
|---|---|
| `paste_volume_alto` | 0.0 % ± 0.0 [0.0–0.0] |
| `cambios_pestana_frecuentes` | 0.0 % ± 0.0 [0.0–0.0] |
| `perdida_foco_prolongada` | 0.0 % ± 0.0 [0.0–0.0] |
| `ritmo_tecleo_atipico` | 0.0 % ± 0.0 [0.0–0.0] |
| `atipico_modelo_poblacional` | 2.9 % ± 2.7 [0.0–8.8] |

## Barrido de dificultad (`ritmo_distinto`, solo modelo)

Separación entre la sesión anómala y la población, en desvíos poblacionales. Muestra cuánto tiene que diferir una sesión para que el Isolation Forest la distinga, sin señales discretas que la delaten.

| Dificultad (σ) | AUC-ROC | EER | Detección modelo | FRR modelo |
|---|---|---|---|---|
| 0 | 0.494 ± 0.072 | 0.500 ± 0.062 | 10.5 % | 9.1 % |
| 0.5 | 0.519 ± 0.071 | 0.481 ± 0.044 | 11.4 % | 9.6 % |
| 1 | 0.572 ± 0.067 | 0.454 ± 0.051 | 14.4 % | 7.9 % |
| 1.5 | 0.636 ± 0.065 | 0.399 ± 0.054 | 16.0 % | 7.5 % |
| 2 | 0.701 ± 0.062 | 0.347 ± 0.062 | 17.2 % | 7.0 % |
| 3 | 0.793 ± 0.055 | 0.286 ± 0.046 | 19.4 % | 5.5 % |

## Sensibilidad: población contaminada (10 % de anómalas)

Misma configuración, pero la línea base incluye sesiones anómalas (como ocurriría en un examen real).

| Componente | FAR | FRR |
|---|---|---|
| Pipeline completo | 14.0 % ± 3.0 [10.0–20.1] | 3.4 % ± 2.6 [0.0–7.5] |
| Solo Isolation Forest | 79.8 % ± 2.8 [76.2–85.0] | 3.4 % ± 2.6 [0.0–7.5] |
| AUC-ROC modelo (`ritmo_distinto`) | 0.910 ± 0.052 [0.809–0.988] | |

## Lectura e interpretación (para el cap. 17/18)

- Con el análisis al cierre, `contamination=0.1` fija que ~10 % de la **cohorte** quede marcada por el modelo (≈ 12 de 120 sesiones), sean o no anómalas. Con 33 % de anómalas en la cohorte (prevalencia elegida para tener suficientes positivos, no realista), la mayoría de las marcas caen en sesiones anómalas: por eso la FRR del modelo es baja y su FAR alto. Con prevalencias realistas (5–10 %) las marcas se reparten distinto: ver `aporte_modelo.md`. AUC, AP y EER usan el score continuo y no dependen de ese umbral.
- En la sección de sensibilidad, la contaminación se agrega a la población, que ya forma parte de la cohorte junto con las sesiones de prueba.
- Los perfiles `pegado_masivo`, `cambio_pestana` y `tecleo_automatizado` se construyeron alrededor de los umbrales de las reglas; que las reglas los detecten es una verificación de que se disparan cuando corresponde, no evidencia de desempeño frente a fraude real.
- El perfil informativo para el componente de IA es `ritmo_distinto` (ver barrido): sin señales discretas, la detección depende enteramente de cuán separada esté la sesión de la línea base poblacional.
- Con pocas sesiones por repetición las métricas tienen variabilidad apreciable; por eso se reportan desvíos e intervalos entre repeticiones y no solo el valor puntual.
- Validez externa pendiente: las anomalías sintéticas no representan necesariamente las conductas reales; el mismo script se puede reutilizar con métricas de sesiones del piloto reemplazando el generador.
