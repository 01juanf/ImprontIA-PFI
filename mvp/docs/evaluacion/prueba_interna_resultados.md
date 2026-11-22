# Prueba interna end-to-end — resultados generados

_Generado por `scripts/prueba_interna.py` el 2026-10-14 18:03 (UTC). No editar a mano: la interpretación está en `prueba_interna.md`._

- Repeticiones por escenario: 3 · semilla del guion: 18 · línea base: 24 sesiones sintéticas normales (semilla 7).
- Navegador: Chromium 141.0.7390.37 (Playwright, headless) · Python 3.12.3 · Linux-6.18.44-fc-v114-x86_64-with-glibc2.39.
- Duración total: 9,3 min.

## Resumen por escenario

| Escenario | Guion | Indicador de regla esperado | Conformes | Indicador del modelo (IF) | UI = API | Sin texto en eventos |
|---|---|---|---|---|---|---|
| `normal` | Mouse + tecleo con ritmo variable (pulsación 60–130 ms, entre teclas 70–220 ms) + 1 salida de pestaña de ~2 s. | ninguno | 3/3 | 0/3 | 3/3 | 3/3 |
| `pegado_masivo` | Tecleo de una frase corta y pegado de un bloque de ~450 caracteres. | `paste_volume_alto` | 3/3 | 0/3 | 3/3 | 3/3 |
| `cambios_foco` | Tecleo con ritmo variable intercalado con 7 salidas de pestaña de 1,5–3 s (simuladas, ver limitación). | `cambios_pestana_frecuentes` | 3/3 | 0/3 | 3/3 | 3/3 |
| `transcripcion` | Tecleo a ritmo constante: pulsación fija de 80 ms y 110 ms entre teclas. | `ritmo_tecleo_atipico` | 3/3 | 0/3 | 3/3 | 3/3 |

_Conforme_ = se generaron todos los indicadores de regla esperados y ningún otro indicador de regla. El indicador del modelo poblacional se informa aparte.

## Detalle por sesión

| Escenario | Rep. | Eventos | Indicadores de regla | IF | Pegado (car.) | Cambios pestaña | Fuera de foco (s) | Pulsación media (ms) | Desvío pulsación (ms) | Entre teclas (ms) | Mouse (px/ms) | Mayor desvío vs. línea base (z) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `normal` | 1 | 301 | — | no | 0 | 1 | 1,8 | 102,7 | 19,2 | 159,5 | 0,56 | `std_dwell_time_ms` -0,6 |
| `pegado_masivo` | 1 | 122 | `paste_volume_alto` | no | 461 | 0 | 0,0 | 96,3 | 19,0 | 142,7 | 0,51 | `std_dwell_time_ms` -0,7 |
| `cambios_foco` | 1 | 325 | `cambios_pestana_frecuentes` | no | 0 | 7 | 15,1 | 98,9 | 19,4 | 272,8 | 0,55 | `mean_flight_time_ms` 3,1 |
| `transcripcion` | 1 | 297 | `ritmo_tecleo_atipico` | no | 0 | 0 | 0,0 | 86,9 | 1,3 | 115,1 | 0,60 | `std_dwell_time_ms` -4,7 |
| `normal` | 2 | 301 | — | no | 0 | 1 | 2,5 | 101,3 | 18,5 | 167,9 | 0,58 | `std_dwell_time_ms` -0,8 |
| `pegado_masivo` | 2 | 122 | `paste_volume_alto` | no | 461 | 0 | 0,0 | 98,3 | 17,8 | 152,4 | 0,61 | `std_dwell_time_ms` -0,9 |
| `cambios_foco` | 2 | 325 | `cambios_pestana_frecuentes` | no | 0 | 7 | 14,9 | 101,3 | 19,5 | 265,3 | 0,59 | `mean_flight_time_ms` 2,9 |
| `transcripcion` | 2 | 297 | `ritmo_tecleo_atipico` | no | 0 | 0 | 0,0 | 87,2 | 2,1 | 114,9 | 0,55 | `std_dwell_time_ms` -4,5 |
| `normal` | 3 | 301 | — | no | 0 | 1 | 1,7 | 102,8 | 20,8 | 162,5 | 0,63 | `mean_dwell_time_ms` 0,5 |
| `pegado_masivo` | 3 | 122 | `paste_volume_alto` | no | 461 | 0 | 0,0 | 101,0 | 20,4 | 142,0 | 0,53 | `mean_flight_time_ms` -0,5 |
| `cambios_foco` | 3 | 325 | `cambios_pestana_frecuentes` | no | 0 | 7 | 16,1 | 98,2 | 20,8 | 266,6 | 0,59 | `mean_flight_time_ms` 3,0 |
| `transcripcion` | 3 | 297 | `ritmo_tecleo_atipico` | no | 0 | 0 | 0,0 | 87,7 | 2,4 | 115,3 | 0,54 | `std_dwell_time_ms` -4,5 |
