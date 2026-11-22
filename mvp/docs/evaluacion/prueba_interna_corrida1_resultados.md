# Prueba interna end-to-end — corrida 1 (12/10/2026, antes del ajuste de captura de teclado del Incremento 9)

_Generado por `scripts/prueba_interna.py` el 2026-10-12 22:05 (UTC); en esta corrida los eventos de teclado todavía incluían el código de tecla. Interpretación en `prueba_interna.md`._

- Repeticiones por escenario: 3 · semilla del guion: 18 · línea base: 24 sesiones sintéticas normales (semilla 7).
- Navegador: Chromium 141.0.7390.37 (Playwright, headless) · Python 3.13.16 · Linux-6.18.44-fc-v114-x86_64-with-glibc2.39.
- Duración total: 9,6 min.

## Resumen por escenario

| Escenario | Guion | Indicador de regla esperado | Conformes | Indicador del modelo (IF) | UI = API | Sin texto en eventos |
|---|---|---|---|---|---|---|
| `normal` | Mouse + tecleo con ritmo variable (pulsación 60–130 ms, entre teclas 70–220 ms) + 1 salida de pestaña de ~2 s. | ninguno | 3/3 | 0/3 | 3/3 | 3/3 |
| `pegado_masivo` | Tecleo de una frase corta y pegado de un bloque de ~450 caracteres. | `paste_volume_alto` | 3/3 | 0/3 | 3/3 | 3/3 |
| `cambios_foco` | Tecleo con ritmo variable intercalado con 7 salidas de pestaña de 1,5–3 s (simuladas, ver limitación). | `cambios_pestana_frecuentes` | 3/3 | 0/3 | 3/3 | 3/3 |
| `transcripcion` | Tecleo a ritmo constante: pulsación fija de 80 ms y 110 ms entre teclas. | `ritmo_tecleo_atipico` | 2/3 | 0/3 | 3/3 | 3/3 |

_Conforme_ = se generaron todos los indicadores de regla esperados y ningún otro indicador de regla. El indicador del modelo poblacional se informa aparte.

## Detalle por sesión

| Escenario | Rep. | Eventos | Indicadores de regla | IF | Pegado (car.) | Cambios pestaña | Fuera de foco (s) | Pulsación media (ms) | Desvío pulsación (ms) | Entre teclas (ms) | Mouse (px/ms) | Mayor desvío vs. línea base (z) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `normal` | 1 | 301 | — | no | 0 | 1 | 1,8 | 103,6 | 19,6 | 160,0 | 0,55 | `mean_dwell_time_ms` 0,6 |
| `pegado_masivo` | 1 | 122 | `paste_volume_alto` | no | 461 | 0 | 0,0 | 97,3 | 19,5 | 143,8 | 0,51 | `mean_mouse_speed_px_ms` -0,6 |
| `cambios_foco` | 1 | 325 | `cambios_pestana_frecuentes` | no | 0 | 7 | 15,1 | 99,3 | 19,5 | 273,3 | 0,54 | `mean_flight_time_ms` 3,1 |
| `transcripcion` | 1 | 297 | — | no | 0 | 0 | 0,0 | 88,5 | 9,1 | 115,7 | 0,60 | `std_dwell_time_ms` -2,9 |
| `normal` | 2 | 301 | — | no | 0 | 1 | 2,5 | 102,2 | 18,3 | 168,5 | 0,58 | `std_dwell_time_ms` -0,8 |
| `pegado_masivo` | 2 | 122 | `paste_volume_alto` | no | 461 | 0 | 0,0 | 99,3 | 18,3 | 153,8 | 0,61 | `std_dwell_time_ms` -0,8 |
| `cambios_foco` | 2 | 325 | `cambios_pestana_frecuentes` | no | 0 | 7 | 14,9 | 100,8 | 19,4 | 265,9 | 0,59 | `mean_flight_time_ms` 2,9 |
| `transcripcion` | 2 | 297 | `ritmo_tecleo_atipico` | no | 0 | 0 | 0,0 | 87,8 | 2,3 | 115,8 | 0,55 | `std_dwell_time_ms` -4,5 |
| `normal` | 3 | 301 | — | no | 0 | 1 | 1,7 | 103,3 | 20,6 | 163,2 | 0,63 | `mean_dwell_time_ms` 0,6 |
| `pegado_masivo` | 3 | 122 | `paste_volume_alto` | no | 461 | 0 | 0,0 | 101,4 | 20,5 | 142,3 | 0,53 | `mean_flight_time_ms` -0,5 |
| `cambios_foco` | 3 | 325 | `cambios_pestana_frecuentes` | no | 0 | 7 | 16,1 | 98,8 | 20,9 | 267,9 | 0,58 | `mean_flight_time_ms` 3,0 |
| `transcripcion` | 3 | 297 | `ritmo_tecleo_atipico` | no | 0 | 0 | 0,0 | 87,5 | 1,8 | 115,5 | 0,54 | `std_dwell_time_ms` -4,6 |
