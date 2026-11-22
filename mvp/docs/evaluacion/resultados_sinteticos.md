# Evaluación del pipeline con datos sintéticos

_Generado por `scripts/evaluar.py` el 2026-10-12 19:08 UTC (scikit-learn 1.5.2, numpy 1.26.4). No editar a mano: regenerar con el script._

> **Advertencia.** Estos números provienen de sesiones **sintéticas** generadas con parámetros elegidos para ejercitar el pipeline, no calibrados con personas reales. Validan que el **procedimiento** de evaluación funciona de punta a punta (eventos → métricas → reglas + Isolation Forest → FAR/FRR/AUC/EER) y muestran cómo se comporta el pipeline frente a anomalías de forma conocida. **No son resultados del piloto ni una estimación del desempeño real** con estudiantes.

## Convención de métricas

Clase positiva = sesión anómala. **FAR** = tasa de anomalías no detectadas (FN/P). **FRR** = tasa de falsas alarmas (FP/N). **EER** = punto donde FAR = FRR. AUC-ROC, AP (average precision) y EER se calculan sobre el score continuo del Isolation Forest (`-decision_function`); las reglas son binarias y solo aportan un punto de operación. Cada celda: media ± desvío entre repeticiones [percentiles 2,5–97,5].

## Protocolo y parámetros

- Repeticiones: **20** (semillas 2026…2045).
- Población (línea base de la evaluación): **40** sesiones, contaminación 0 % (mínimo técnico del modelo: 20).
- Prueba por repetición: **40** normales + **40** anómalas, repartidas en partes iguales entre: pegado_masivo, cambio_pestana, tecleo_automatizado, ritmo_distinto.
- Pipeline evaluado tal como está en el MVP (sin ajustar con las etiquetas): umbrales {'paste_chars_total': 200.0, 'tab_switch_count': 5.0, 'focus_loss_duration_total_ms': 60000.0, 'std_dwell_time_ms_low': 5.0}; Isolation Forest `n_estimators=200`, `contamination=0.1`, `random_state=0`.
- Población normal: dwell ~ N(95.0, 15.0) ms entre participantes, desvío intra-sesión U(15.0, 30.0); flight ~ N(160.0, 35.0) ms, intra U(40.0, 80.0); 250–500 pulsaciones; mouse ~ N(0.6, 0.15) px/ms (CV intra 0.3); cambios de pestaña ~ Poisson(0.6) con duración media 4000 ms; pegado chico con prob. 0.2 (5–60 caracteres).
- Dificultad de `ritmo_distinto`: **2.0** desvíos poblacionales en dwell, flight y velocidad de mouse.

## Resultados globales

| Componente | FAR (anomalías no detectadas) | FRR (falsas alarmas) |
|---|---|---|
| Pipeline completo (reglas ∨ modelo) | 3.6 % ± 4.2 [0.0–12.6] | 11.7 % ± 6.7 [1.2–25.1] |
| Solo reglas determinísticas | 25.0 % ± 0.0 [25.0–25.0] | 0.0 % ± 0.0 [0.0–0.0] |
| Solo Isolation Forest | 65.0 % ± 10.8 [51.2–85.1] | 11.7 % ± 6.7 [1.2–25.1] |

Score continuo del Isolation Forest (todas las anomalías vs. normales):

| AUC-ROC | AP | EER |
|---|---|---|
| 0.669 ± 0.047 [0.601–0.755] | 0.704 ± 0.052 [0.626–0.784] | 0.390 ± 0.051 [0.287–0.476] |

## Por perfil de anomalía

| Perfil | Detección pipeline | Detección reglas | Detección modelo | AUC-ROC modelo | EER modelo |
|---|---|---|---|---|---|
| `pegado_masivo` | 100.0 % ± 0.0 [100.0–100.0] | 100.0 % ± 0.0 [100.0–100.0] | 19.0 % ± 19.4 [0.0–60.5] | 0.547 ± 0.115 [0.398–0.765] | 0.463 ± 0.092 [0.300–0.600] |
| `cambio_pestana` | 100.0 % ± 0.0 [100.0–100.0] | 100.0 % ± 0.0 [100.0–100.0] | 11.5 % ± 10.9 [0.0–30.0] | 0.475 ± 0.108 [0.336–0.712] | 0.515 ± 0.086 [0.334–0.626] |
| `tecleo_automatizado` | 100.0 % ± 0.0 [100.0–100.0] | 100.0 % ± 0.0 [100.0–100.0] | 24.0 % ± 13.5 [0.0–40.0] | 0.715 ± 0.050 [0.630–0.803] | 0.358 ± 0.056 [0.275–0.463] |
| `ritmo_distinto` | 85.5 % ± 16.7 [49.5–100.0] | 0.0 % ± 0.0 [0.0–0.0] | 85.5 % ± 16.7 [49.5–100.0] | 0.940 ± 0.038 [0.881–0.994] | 0.134 ± 0.066 [0.025–0.213] |

Falsas alarmas sobre sesiones normales, por indicador:

| Indicador | Tasa sobre normales |
|---|---|
| `paste_volume_alto` | 0.0 % ± 0.0 [0.0–0.0] |
| `cambios_pestana_frecuentes` | 0.0 % ± 0.0 [0.0–0.0] |
| `perdida_foco_prolongada` | 0.0 % ± 0.0 [0.0–0.0] |
| `ritmo_tecleo_atipico` | 0.0 % ± 0.0 [0.0–0.0] |
| `atipico_modelo_poblacional` | 11.7 % ± 6.7 [1.2–25.1] |

## Barrido de dificultad (`ritmo_distinto`, solo modelo)

Separación entre la sesión anómala y la población, en desvíos poblacionales. Muestra cuánto tiene que diferir una sesión para que el Isolation Forest la distinga, sin señales discretas que la delaten.

| Dificultad (σ) | AUC-ROC | EER | Detección modelo | FRR modelo |
|---|---|---|---|---|
| 0 | 0.493 ± 0.070 | 0.508 ± 0.059 | 14.0 % | 11.7 % |
| 0.5 | 0.556 ± 0.074 | 0.465 ± 0.051 | 20.0 % | 11.7 % |
| 1 | 0.699 ± 0.080 | 0.345 ± 0.070 | 36.1 % | 11.7 % |
| 1.5 | 0.839 ± 0.062 | 0.236 ± 0.063 | 61.2 % | 11.7 % |
| 2 | 0.932 ± 0.042 | 0.136 ± 0.048 | 84.1 % | 11.7 % |
| 3 | 0.989 ± 0.012 | 0.048 ± 0.036 | 98.5 % | 11.7 % |

## Sensibilidad: población contaminada (10 % de anómalas)

Misma configuración, pero la línea base incluye sesiones anómalas (como ocurriría en un examen real).

| Componente | FAR | FRR |
|---|---|---|
| Pipeline completo | 6.1 % ± 4.5 [1.2–16.4] | 7.0 % ± 6.7 [0.0–21.3] |
| Solo Isolation Forest | 56.2 % ± 8.5 [43.7–73.8] | 7.0 % ± 6.7 [0.0–21.3] |
| AUC-ROC modelo (`ritmo_distinto`) | 0.942 ± 0.038 [0.864–0.988] | |

## Lectura e interpretación (para el cap. 17/18)

- La FRR del Isolation Forest queda cerca de `contamination=0.1` **por construcción**: el umbral se fija para que ~10 % de la población de entrenamiento quede marcada. Es una tasa de revisión elegida por diseño, no una tasa de fraude estimada.
- Los perfiles `pegado_masivo`, `cambio_pestana` y `tecleo_automatizado` se construyeron alrededor de los umbrales de las reglas; que las reglas los detecten es una verificación de que se disparan cuando corresponde, no evidencia de desempeño frente a fraude real.
- El perfil informativo para el componente de IA es `ritmo_distinto` (ver barrido): sin señales discretas, la detección depende enteramente de cuán separada esté la sesión de la línea base poblacional.
- Con pocas sesiones por repetición las métricas tienen variabilidad apreciable; por eso se reportan desvíos e intervalos entre repeticiones y no solo el valor puntual.
- Validez externa pendiente: las anomalías sintéticas no representan necesariamente las conductas reales; el mismo script se puede reutilizar con métricas de sesiones del piloto reemplazando el generador.
