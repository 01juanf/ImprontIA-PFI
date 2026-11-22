# Prueba interna end-to-end — resultados generados

_Generado por `scripts/prueba_interna.py` el 2026-10-21 22:33 (UTC). No editar a mano: la interpretación está en `prueba_interna.md`._

- Repeticiones por escenario: 3 · semilla del guion: 18 · línea base: 24 sesiones sintéticas normales (semilla 7).
- Navegador: Chromium 141.0.7390.37 (Playwright, headless) · Python 3.12.3 · Linux-6.18.44-fc-v139-x86_64-with-glibc2.39.
- Duración total: 10,2 min.

## Resumen por escenario

| Escenario | Guion | Indicador de regla esperado | Conformes | Indicador del modelo (IF) | UI = API | Sin texto en eventos | Respuesta guardada |
|---|---|---|---|---|---|---|---|
| `normal` | Mouse + tecleo con ritmo variable (pulsación 60–130 ms, entre teclas 70–220 ms) + 1 salida de pestaña de ~2 s. | ninguno | 3/3 | 0/3 | 3/3 | 3/3 | 3/3 |
| `pegado_masivo` | Tecleo de una frase corta y pegado de un bloque de ~450 caracteres. | `paste_volume_alto` | 3/3 | 0/3 | 3/3 | 3/3 | 3/3 |
| `cambios_foco` | Tecleo con ritmo variable intercalado con 7 salidas de pestaña de 1,5–3 s (simuladas, ver limitación). | `cambios_pestana_frecuentes` | 3/3 | 0/3 | 3/3 | 3/3 | 3/3 |
| `transcripcion` | Tecleo a ritmo constante: pulsación fija de 80 ms y 110 ms entre teclas. | `ritmo_tecleo_atipico` | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |

_Conforme_ = se generaron todos los indicadores de regla esperados y ningún otro indicador de regla. El indicador del modelo poblacional se informa aparte: desde el Incremento 16 se calcula al cerrar la evaluación, sobre la cohorte completa (línea base sintética + la sesión de navegador).

## Detalle por sesión

| Escenario | Rep. | Eventos | Indicadores de regla | IF | Pegado (car.) | Cambios pestaña | Fuera de foco (s) | Pulsación media (ms) | Desvío pulsación (ms) | Entre teclas (ms) | Mouse (px/ms) | Mayor desvío vs. línea base (z) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `normal` | 1 | 301 | — | no | 0 | 1 | 1,8 | 107,1 | 19,6 | 161,3 | 0,55 | `mean_dwell_time_ms` 0,8 |
| `pegado_masivo` | 1 | 122 | `paste_volume_alto` | no | 461 | 0 | 0,0 | 101,7 | 23,4 | 144,7 | 0,50 | `mean_mouse_speed_px_ms` -0,7 |
| `cambios_foco` | 1 | 325 | `cambios_pestana_frecuentes` | no | 0 | 7 | 15,1 | 102,2 | 19,5 | 274,5 | 0,54 | `mean_flight_time_ms` 3,2 |
| `transcripcion` | 1 | 297 | `ritmo_tecleo_atipico` | sí | 0 | 0 | 0,0 | 88,9 | 2,5 | 115,5 | 0,60 | `std_dwell_time_ms` -4,4 |
| `normal` | 2 | 301 | — | no | 0 | 1 | 2,5 | 103,4 | 18,3 | 168,8 | 0,58 | `std_dwell_time_ms` -0,8 |
| `pegado_masivo` | 2 | 122 | `paste_volume_alto` | no | 461 | 0 | 0,0 | 99,9 | 18,0 | 153,1 | 0,61 | `std_dwell_time_ms` -0,9 |
| `cambios_foco` | 2 | 325 | `cambios_pestana_frecuentes` | no | 0 | 7 | 14,9 | 102,2 | 19,3 | 265,7 | 0,59 | `mean_flight_time_ms` 2,9 |
| `transcripcion` | 2 | 297 | `ritmo_tecleo_atipico` | sí | 0 | 0 | 0,0 | 88,5 | 2,8 | 115,4 | 0,56 | `std_dwell_time_ms` -4,4 |
| `normal` | 3 | 301 | — | no | 0 | 1 | 1,7 | 104,6 | 21,3 | 163,7 | 0,62 | `mean_dwell_time_ms` 0,7 |
| `pegado_masivo` | 3 | 122 | `paste_volume_alto` | no | 461 | 0 | 0,0 | 104,2 | 20,2 | 144,0 | 0,53 | `mean_dwell_time_ms` 0,6 |
| `cambios_foco` | 3 | 325 | `cambios_pestana_frecuentes` | no | 0 | 7 | 16,1 | 99,2 | 20,9 | 267,7 | 0,58 | `mean_flight_time_ms` 3,0 |
| `transcripcion` | 3 | 297 | `ritmo_tecleo_atipico` | sí | 0 | 0 | 0,0 | 90,9 | 2,8 | 117,5 | 0,54 | `std_dwell_time_ms` -4,4 |
