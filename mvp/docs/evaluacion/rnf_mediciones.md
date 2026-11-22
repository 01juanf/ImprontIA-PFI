# Mediciones de requisitos no funcionales de rendimiento (RNF07, RNF09, RNF11)

_Generado por `scripts/medir_rnf.py --informe` el 2026-10-21 23:23 UTC a partir de `rnf_mediciones_postgres.json`, `rnf_mediciones_sqlite.json`. No editar a mano: regenerar con el script._

> Mediciones sobre el sistema real (backend FastAPI con uvicorn en un proceso, como el Dockerfile; dashboard compilado en Chromium) con sesiones **sintéticas** (`app/evaluation/synthetic.py`). Los tiempos de servidor se miden del lado del cliente HTTP, en la misma máquina que el servidor. Valores p50 / p95 / máximo.

## Entorno

| Corrida | CPU | RAM | SO | Python | Base |
|---|---|---|---|---|---|
| postgres | 2 × Intel(R) Xeon(R) Processor @ 2.80GHz | 7.8 GB | Linux-6.18.44-fc-v139-x86_64-with-glibc2.39 | 3.12.3 | postgresql 16.15 (Ubuntu 16.15-0ubuntu0.24.04.1) |
| sqlite | 2 × Intel(R) Xeon(R) Processor @ 2.80GHz | 7.8 GB | Linux-6.18.44-fc-v139-x86_64-with-glibc2.39 | 3.12.3 | sqlite 3.45.1 |

## Resultados

| Requisito | Cota | Medición | Corrida | p50 / p95 / máx | Resultado |
|---|---|---|---|---|---|
| RNF11 procesamiento por sesión | 5 s | `/end` → indicadores disponibles, 500 sesiones (~838 eventos c/u) | postgres | 49 / 176 / 240 ms | cumple |
| RNF11 procesamiento por sesión | 5 s | sesión de ~857 eventos (n=5) | postgres | 47 / 48 / 48 ms | cumple |
| RNF11 procesamiento por sesión | 5 s | sesión de ~8991 eventos (n=5) | postgres | 371 / 553 / 566 ms | cumple |
| RNF11 procesamiento por sesión | 5 s | sesión de ~42841 eventos (n=3) | postgres | 1741 / 2089 / 2128 ms | cumple |
| RNF11 consultas docentes | 2 s | listado de sesiones, 500 sesiones, evaluación abierta | postgres | 45 / 170 / 217 ms | cumple |
| RNF11 consultas docentes | 2 s | detalle de sesión, 500 sesiones, evaluación abierta | postgres | 15 / 19 / 21 ms | cumple |
| RNF11 consultas docentes | 2 s | panorama, 500 sesiones, evaluación abierta | postgres | 71 / 229 / 264 ms | cumple |
| RNF11 consultas docentes | 2 s | listado de sesiones, 500 sesiones, evaluación cerrada | postgres | 44 / 175 / 230 ms | cumple |
| RNF11 consultas docentes | 2 s | detalle de sesión, 500 sesiones, evaluación cerrada | postgres | 15 / 20 / 23 ms | cumple |
| RNF11 consultas docentes | 2 s | panorama, 500 sesiones, evaluación cerrada | postgres | 74 / 212 / 264 ms | cumple |
| (Inc. 16) cierre de la evaluación | sin cota | `POST /exams/{id}/cerrar`, 500 sesiones (1 medición) | postgres | 9.50 s | — |
| (Inc. 16) modelo sobre la cohorte | sin cota | `analizar_cohorte` fuera de línea (n=3) | postgres | 6.77 / 7.13 / 7.17 s | — |
| RNF09 concurrencia | 200 sesiones activas | lotes cada 5 s durante 60 s (2419 lotes, 0 errores) | postgres | 88 / 403 / 796 ms | cumple |
| RNF09 + RNF11 consultas bajo carga | 2 s | listado (500 sesiones) con 200 activas | postgres | 102 / 328 / 523 ms | cumple |
| RNF09 + RNF11 consultas bajo carga | 2 s | detalle (500 sesiones) con 200 activas | postgres | 47 / 265 / 399 ms | cumple |
| RNF09 + RNF11 consultas bajo carga | 2 s | panorama (500 sesiones) con 200 activas | postgres | 267 / 481 / 562 ms | cumple |
| RNF09 + RNF11 entrega simultánea | 5 s | 200 `/end` a la vez (2 errores) | postgres | 5621 / 10428 / 10501 ms | **no cumple** |
| RNF11 procesamiento por sesión | 5 s | `/end` → indicadores disponibles, 500 sesiones (~838 eventos c/u) | sqlite | 41 / 170 / 272 ms | cumple |
| RNF11 procesamiento por sesión | 5 s | sesión de ~857 eventos (n=5) | sqlite | 46 / 136 / 155 ms | cumple |
| RNF11 procesamiento por sesión | 5 s | sesión de ~8991 eventos (n=5) | sqlite | 516 / 591 / 606 ms | cumple |
| RNF11 procesamiento por sesión | 5 s | sesión de ~42841 eventos (n=3) | sqlite | 1816 / 1891 / 1899 ms | cumple |
| RNF11 consultas docentes | 2 s | listado de sesiones, 500 sesiones, evaluación abierta | sqlite | 40 / 163 / 176 ms | cumple |
| RNF11 consultas docentes | 2 s | detalle de sesión, 500 sesiones, evaluación abierta | sqlite | 11 / 14 / 16 ms | cumple |
| RNF11 consultas docentes | 2 s | panorama, 500 sesiones, evaluación abierta | sqlite | 63 / 198 / 207 ms | cumple |
| RNF11 consultas docentes | 2 s | listado de sesiones, 500 sesiones, evaluación cerrada | sqlite | 38 / 173 / 193 ms | cumple |
| RNF11 consultas docentes | 2 s | detalle de sesión, 500 sesiones, evaluación cerrada | sqlite | 11 / 13 / 14 ms | cumple |
| RNF11 consultas docentes | 2 s | panorama, 500 sesiones, evaluación cerrada | sqlite | 66 / 197 / 211 ms | cumple |
| (Inc. 16) cierre de la evaluación | sin cota | `POST /exams/{id}/cerrar`, 500 sesiones (1 medición) | sqlite | 8.26 s | — |
| (Inc. 16) modelo sobre la cohorte | sin cota | `analizar_cohorte` fuera de línea (n=3) | sqlite | 6.70 / 6.72 / 6.73 s | — |
| RNF09 concurrencia | 200 sesiones activas | lotes cada 5 s durante 60 s (2440 lotes, 5 errores) | sqlite | 97 / 1595 / 5254 ms | **no cumple** |
| RNF09 + RNF11 consultas bajo carga | 2 s | listado (500 sesiones) con 200 activas | sqlite | 79 / 249 / 364 ms | cumple |
| RNF09 + RNF11 consultas bajo carga | 2 s | detalle (500 sesiones) con 200 activas | sqlite | 54 / 147 / 330 ms | cumple |
| RNF09 + RNF11 consultas bajo carga | 2 s | panorama (500 sesiones) con 200 activas | sqlite | 186 / 370 / 440 ms | cumple |
| RNF09 + RNF11 entrega simultánea | 5 s | 200 `/end` a la vez (4 errores) | sqlite | 4830 / 8488 / 9044 ms | **no cumple** |
| RNF07 costo por evento en el navegador | 50 ms | handlers de captura, CPU ×1 (1498 ejecuciones; 0 tareas largas) | sqlite | 0.000 / 0.100 / 0.400 ms | cumple |
| RNF07 costo por evento en el navegador | 50 ms | handlers de captura, CPU ×4 (1498 ejecuciones; 0 tareas largas) | sqlite | 0.000 / 0.600 / 3.500 ms | cumple |

## Detalle

### Corrida `postgres` (2026-10-21 23:11 UTC)

Parámetros: `{"etiqueta": "postgres", "db_url": "postgresql://imp:imp@localhost/imp_rnf", "pruebas": "rnf11,rnf09", "sesiones": 500, "barrido": [1, 10, 50], "repeticiones": 30, "concurrentes": 200, "duracion_carga": 60, "semilla": 2026, "api_port": 8132, "web_port": 5191, "backend_python": "mvp/backend/.venv/bin/python", "salida": "mvp/docs/evaluacion"}`.
Carga del sistema (loadavg 1/5/15 min) antes y después de cada fase: `{'antes': [0.96142578125, 1.03515625, 1.29443359375], 'tras_rnf11': [1.392578125, 1.15380859375, 1.2802734375], 'tras_rnf09': [4.07861328125, 2.23291015625, 1.66015625]}` (otros procesos de la máquina compartida también la afectan).

- Cohorte: 500 sesiones, 419221 eventos en total (por sesión p50 848, máx 1142); carga por la API en 118 s. Detalle verificado tras `/end`: True.
- Cierre: 9.50 s; cobertura tras el cierre: {'evaluacion_cerrada': True, 'sesiones_evaluadas': 500, 'sesiones_no_evaluadas': 0, 'sesiones_pendientes': 0}. Sesiones marcadas por el modelo (fuera de línea): 50.
- Consultas con la evaluación abierta: errores 0; media listado 61 ms, detalle 15 ms, panorama 114 ms.
- Consultas con la evaluación cerrada: errores 0; media listado 60 ms, detalle 16 ms, panorama 117 ms.
- Concurrencia: 2419 lotes (40.3/s), 118070 eventos guardados, errores de lotes 0, errores de consultas 0, ráfaga de 200 entregas completada en 10.6 s (errores 2). Errores por tipo: {'events:ReadError:reintentado': 98, 'end:RemoteProtocolError': 2}.

### Corrida `sqlite` (2026-10-21 23:16 UTC)

Parámetros: `{"etiqueta": "sqlite", "db_url": null, "pruebas": "rnf11,rnf09,rnf07", "sesiones": 500, "barrido": [1, 10, 50], "repeticiones": 30, "concurrentes": 200, "duracion_carga": 60, "semilla": 2026, "api_port": 8131, "web_port": 5191, "backend_python": "mvp/backend/.venv/bin/python", "salida": "mvp/docs/evaluacion"}`.
Carga del sistema (loadavg 1/5/15 min) antes y después de cada fase: `{'antes': [4.07861328125, 2.23291015625, 1.66015625], 'tras_rnf11': [1.21142578125, 1.71728515625, 1.56103515625], 'tras_rnf09': [1.828125, 1.86669921875, 1.6318359375]}` (otros procesos de la máquina compartida también la afectan).

- Cohorte: 500 sesiones, 419221 eventos en total (por sesión p50 848, máx 1142); carga por la API en 106 s. Detalle verificado tras `/end`: True.
- Cierre: 8.26 s; cobertura tras el cierre: {'evaluacion_cerrada': True, 'sesiones_evaluadas': 500, 'sesiones_no_evaluadas': 0, 'sesiones_pendientes': 0}. Sesiones marcadas por el modelo (fuera de línea): 50.
- Consultas con la evaluación abierta: errores 0; media listado 53 ms, detalle 11 ms, panorama 105 ms.
- Consultas con la evaluación cerrada: errores 0; media listado 54 ms, detalle 11 ms, panorama 106 ms.
- Concurrencia: 2440 lotes (40.7/s), 118661 eventos guardados, errores de lotes 5, errores de consultas 0, ráfaga de 200 entregas completada en 9.2 s (errores 4). Errores por tipo: {'events:ReadError:reintentado': 52, 'events:500': 5, 'events:RemoteProtocolError:reintentado': 1, 'end:503': 3, 'end:500': 1}.
- Navegador: Chromium 141.0.7390.37 (headless).
  - CPU ×1: 274 caracteres en 52 s; keydown n=274 máx 0.40 ms, keyup n=274 máx 0.20 ms, mousemove n=950 máx 0.20 ms. Tareas largas: 0 (máx 0 ms). Event Timing (página completa, entradas ≥ 16 ms): 583, procesamiento máx 2.3 ms, duración máx 24.0 ms.
  - CPU ×4: 274 caracteres en 56 s; keydown n=274 máx 2.30 ms, keyup n=274 máx 3.50 ms, mousemove n=950 máx 1.70 ms. Tareas largas: 0 (máx 0 ms). Event Timing (página completa, entradas ≥ 16 ms): 1073, procesamiento máx 13.2 ms, duración máx 32.0 ms.

## Limitaciones

- **Datos sintéticos.** Volumen y forma de los eventos vienen del generador de la evaluación (≈ 2 minutos de escritura por sesión); un examen real dura más. El barrido por tamaño de sesión cubre sesiones más largas.
- **Una sola máquina.** Cliente de carga (hilos de Python), servidor y base comparten las mismas CPU: los tiempos incluyen la contención del propio generador de carga (pesimista para el servidor) y no incluyen la latencia de una red real ni la de un servicio gestionado (Render, Neon).
- **Un proceso de uvicorn**, como el Dockerfile; con más procesos o más CPU los números cambian.
- **Reintentos.** Como `syncQueue.ts`, el generador reintenta una vez un lote que falla por un error de transporte (conexión cerrada por el servidor al vencer su keep-alive de 5 s, igual al intervalo de envío); esos casos figuran como `…:reintentado` en los errores por tipo y solo cuentan como error si el reintento también falla. `/end` no se reintenta (en el dashboard el reintento es manual).
- **El cierre se mide una vez por corrida** (es una operación única por evaluación); el costo del modelo se repite fuera de línea.
- **RNF07** mide los handlers de captura registrados en `document`/`window` (capture.ts + keyPairing.ts, incluido el encolado del evento), no el renderizado de React del área de texto, que se informa aparte (Event Timing). Chromium headless; `performance.now()` tiene resolución reducida (≈ 0,1 ms) sin aislamiento de origen, por lo que los valores por debajo de esa resolución aparecen como 0 o 0,1 ms.
