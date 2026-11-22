# Aporte del modelo poblacional sobre las reglas (datos sintéticos)

_Generado por `scripts/aporte_modelo.py` el 2026-10-21 22:30 UTC (scikit-learn 1.5.2, numpy 1.26.4), 30 semillas (2026…2055), 498 s. No editar las tablas a mano: regenerar con el script. Datos por semilla en `aporte_modelo.csv`._

> **Advertencia.** Sesiones **sintéticas**, con parámetros no calibrados con personas. Los números muestran cómo se reparten las detecciones entre reglas y modelo para anomalías de forma conocida; **no** estiman el desempeño con estudiantes ni están validados con personas.

## Método

- Protocolo de **cohorte al cierre** (Incremento 16): por semilla se genera una cohorte de N sesiones, se calculan las métricas con `features.compute_all_features`, las reglas con `indicators.generate_indicators` (sin reglas de examen) y el modelo con **una** llamada a `cohort.analizar_cohorte` sobre todas las sesiones (métricas continuas, Isolation Forest `contamination=0.1`, mínimo 20 sesiones). La marca del modelo es `indicator_from_anomaly`. Lo que ve el docente ("requiere revisión") es reglas ∨ modelo.
- Cohortes de N = 40, 100. **Por condición**: 10 % de la cohorte es de esa condición y el resto normal. **Mixta**: 5 % de cada condición (20 % no normal en total).
- Correspondencia condición → perfil sintético del Incremento 6: `pegado` → `pegado_masivo`, `transcripcion` → `tecleo_automatizado`, `consulta_externa` → `cambio_pestana`, `suplantacion` → `ritmo_distinto` (dificultad 2σ; sensibilidad con 1σ). Los tres primeros perfiles se construyeron alrededor de los umbrales de las reglas ({'paste_chars_total': 200.0, 'tab_switch_count': 5.0, 'focus_loss_duration_total_ms': 60000.0, 'std_dwell_time_ms_low': 5.0}); `transcripcion` como tecleo casi constante es el caso más favorable a la regla y una transcripción humana real probablemente no lo sea.
- Recall = proporción de sesiones de la condición marcadas; FPR = proporción de sesiones normales de la misma cohorte marcadas. **Recall incremental** = marcadas por el modelo y no por las reglas. **FPR incremental** = normales marcadas solo por el modelo. Cada celda: media entre semillas, en %, con IC 95 % (t de Student) entre semillas. La detección es transductiva: las sesiones anómalas también forman parte de la población con la que se ajusta el modelo, como en un examen real.

## Resultados por condición (cohorte con 10 % de la condición)

| Condición | N | Recall reglas | Recall modelo | Recall reglas ∨ modelo | **Recall incremental** | FPR reglas | FPR modelo | FPR reglas ∨ modelo |
|---|---|---|---|---|---|---|---|---|
| `pegado` | 40 | 100.0 [100.0–100.0] | 8.3 [3.9–12.8] | 100.0 [100.0–100.0] | **0.0 [0.0–0.0]** | 0.0 [0.0–0.0] | 10.2 [9.7–10.7] | 10.2 [9.7–10.7] |
| `pegado` | 100 | 100.0 [100.0–100.0] | 13.0 [9.3–16.7] | 100.0 [100.0–100.0] | **0.0 [0.0–0.0]** | 0.0 [0.0–0.0] | 9.7 [9.3–10.1] | 9.7 [9.3–10.1] |
| `transcripcion` | 40 | 100.0 [100.0–100.0] | 42.5 [34.3–50.7] | 100.0 [100.0–100.0] | **0.0 [0.0–0.0]** | 0.0 [0.0–0.0] | 6.4 [5.5–7.3] | 6.4 [5.5–7.3] |
| `transcripcion` | 100 | 100.0 [100.0–100.0] | 42.0 [37.5–46.5] | 100.0 [100.0–100.0] | **0.0 [0.0–0.0]** | 0.0 [0.0–0.0] | 6.4 [5.9–6.9] | 6.4 [5.9–6.9] |
| `consulta_externa` | 40 | 100.0 [100.0–100.0] | 14.2 [8.9–19.5] | 100.0 [100.0–100.0] | **0.0 [0.0–0.0]** | 0.0 [0.0–0.0] | 9.5 [8.9–10.1] | 9.5 [8.9–10.1] |
| `consulta_externa` | 100 | 100.0 [100.0–100.0] | 10.3 [6.6–14.1] | 100.0 [100.0–100.0] | **0.0 [0.0–0.0]** | 0.0 [0.0–0.0] | 10.0 [9.5–10.4] | 10.0 [9.5–10.4] |
| `suplantacion` | 40 | 0.0 [0.0–0.0] | 62.5 [56.6–68.4] | 62.5 [56.6–68.4] | **62.5 [56.6–68.4]** | 0.0 [0.0–0.0] | 4.2 [3.5–4.8] | 4.2 [3.5–4.8] |
| `suplantacion` | 100 | 0.0 [0.0–0.0] | 54.0 [49.9–58.1] | 54.0 [49.9–58.1] | **54.0 [49.9–58.1]** | 0.0 [0.0–0.0] | 5.1 [4.7–5.6] | 5.1 [4.7–5.6] |

## Cohorte mixta (5 % de cada condición)

| Condición | N | Recall reglas | Recall modelo | Recall reglas ∨ modelo | **Recall incremental** | FPR reglas | FPR modelo | FPR reglas ∨ modelo |
|---|---|---|---|---|---|---|---|---|
| `pegado` | 40 | 100.0 [100.0–100.0] | 1.7 [0.0–5.1] | 100.0 [100.0–100.0] | **0.0 [0.0–0.0]** | 0.0 [0.0–0.0] | 3.8 [2.9–4.6] | 3.8 [2.9–4.6] |
| `pegado` | 100 | 100.0 [100.0–100.0] | 3.3 [0.5–6.2] | 100.0 [100.0–100.0] | **0.0 [0.0–0.0]** | 0.0 [0.0–0.0] | 3.8 [3.2–4.3] | 3.8 [3.2–4.3] |
| `transcripcion` | 40 | 100.0 [100.0–100.0] | 66.7 [55.3–78.0] | 100.0 [100.0–100.0] | **0.0 [0.0–0.0]** | 0.0 [0.0–0.0] | 3.8 [2.9–4.6] | 3.8 [2.9–4.6] |
| `transcripcion` | 100 | 100.0 [100.0–100.0] | 70.0 [63.9–76.1] | 100.0 [100.0–100.0] | **0.0 [0.0–0.0]** | 0.0 [0.0–0.0] | 3.8 [3.2–4.3] | 3.8 [3.2–4.3] |
| `consulta_externa` | 40 | 100.0 [100.0–100.0] | 5.0 [0.0–10.7] | 100.0 [100.0–100.0] | **0.0 [0.0–0.0]** | 0.0 [0.0–0.0] | 3.8 [2.9–4.6] | 3.8 [2.9–4.6] |
| `consulta_externa` | 100 | 100.0 [100.0–100.0] | 2.7 [0.1–5.2] | 100.0 [100.0–100.0] | **0.0 [0.0–0.0]** | 0.0 [0.0–0.0] | 3.8 [3.2–4.3] | 3.8 [3.2–4.3] |
| `suplantacion` | 40 | 0.0 [0.0–0.0] | 66.7 [53.4–79.9] | 66.7 [53.4–79.9] | **66.7 [53.4–79.9]** | 0.0 [0.0–0.0] | 3.8 [2.9–4.6] | 3.8 [2.9–4.6] |
| `suplantacion` | 100 | 0.0 [0.0–0.0] | 63.3 [54.3–72.3] | 63.3 [54.3–72.3] | **63.3 [54.3–72.3]** | 0.0 [0.0–0.0] | 3.8 [3.2–4.3] | 3.8 [3.2–4.3] |

## Sensibilidad: `suplantacion` con dificultad 1σ

| Condición | N | Recall reglas | Recall modelo | Recall reglas ∨ modelo | **Recall incremental** | FPR reglas | FPR modelo | FPR reglas ∨ modelo |
|---|---|---|---|---|---|---|---|---|
| `suplantacion` | 40 | 0.0 [0.0–0.0] | 24.2 [17.5–30.9] | 24.2 [17.5–30.9] | **24.2 [17.5–30.9]** | 0.0 [0.0–0.0] | 8.4 [7.7–9.2] | 8.4 [7.7–9.2] |
| `suplantacion` | 100 | 0.0 [0.0–0.0] | 25.7 [21.3–30.0] | 25.7 [21.3–30.0] | **25.7 [21.3–30.0]** | 0.0 [0.0–0.1] | 8.3 [7.8–8.7] | 8.3 [7.8–8.8] |

## Dependencia del orden

- Permutar el orden en que se entregan las sesiones a `analizar_cohorte` (mismos identificadores): marcas y scores **idénticos en 60 de 60 cohortes** (chequeo corrido en las primeras 5 semillas de cada escenario y N). El resultado no depende del orden de llegada.
- Reasignar los identificadores (el modelo ordena por id, un UUID aleatorio, y el Isolation Forest submuestrea por posición con `random_state=0`): la marca del modelo coincide en el 100.0 % de las sesiones en promedio (mínimo por cohorte 100.0 %). Las marcas tampoco cambian con otra asignación de identificadores.

## Los z-scores no explican la decisión del modelo

Junto a cada marca del modelo se listan las dos métricas con mayor |z| respecto de la cohorte (`anomaly._top_deviating_features`). Son desvíos descriptivos univariados, calculados aparte del Isolation Forest: no dicen qué divisiones aislaron a la sesión. En estas cohortes, de 2520 marcas del modelo, el 17.4 % tiene su mayor |z| por debajo de 2 y el 0.2 % por debajo de 1,5 (una parte de las marcas no tiene ninguna métrica individual extrema). Deben presentarse como "en qué métricas se aleja más de la cohorte", no como el motivo de la marca.

## Interpretación

- `pegado`: el modelo **no agrega ninguna detección**: todo lo que marca ya lo marcaban las reglas (N = 40: reglas 100.0 %, incremental del modelo 0.0 %; N = 100: reglas 100.0 %, incremental del modelo 0.0 %).
- `transcripcion`: el modelo **no agrega ninguna detección**: todo lo que marca ya lo marcaban las reglas (N = 40: reglas 100.0 %, incremental del modelo 0.0 %; N = 100: reglas 100.0 %, incremental del modelo 0.0 %).
- `consulta_externa`: el modelo **no agrega ninguna detección**: todo lo que marca ya lo marcaban las reglas (N = 40: reglas 100.0 %, incremental del modelo 0.0 %; N = 100: reglas 100.0 %, incremental del modelo 0.0 %).
- `suplantacion`: las detecciones de esta condición vienen del modelo (N = 40: reglas 0.0 %, incremental del modelo 62.5 %; N = 100: reglas 0.0 %, incremental del modelo 54.0 %).
- Costo: en sesiones normales las reglas casi no disparan con estos parámetros, así que prácticamente todas las falsas alarmas del pipeline las agrega el modelo (FPR incremental medio, condiciones juntas: N = 40: 7.6 %; N = 100: 7.8 %). Es la tasa de revisión fijada por `contamination=0.1` repartida entre normales y anómalas de la cohorte, no una tasa de fraude.

## Limitaciones

- Datos sintéticos, no validados con personas. Los perfiles de `pegado`, `consulta_externa` y `transcripcion` se definieron alrededor de los umbrales de las reglas, así que el 100 % de las reglas y el aporte nulo del modelo en esas condiciones son en buena parte consecuencia del diseño del generador. El aporte del modelo en `suplantacion` depende de cuánto se separe el ritmo de la persona de la cohorte (ver sensibilidad y `barrido_dificultad.csv`); con personas reales esa separación es desconocida.
- La correspondencia condición → perfil es una analogía. En particular, una transcripción humana no produce un tecleo casi constante; en esa condición el resultado real puede ser muy distinto.
- Con N = 40 y 10 % de prevalencia hay 4 sesiones de la condición por cohorte: el recall por cohorte toma pocos valores y los intervalos entre semillas son anchos.
- El modelo no ve las métricas discretas (pegado, pestañas): por diseño solo complementa a las reglas en la dinámica continua de teclado y mouse.

