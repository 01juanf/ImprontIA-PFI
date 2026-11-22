# Prueba de resiliencia de la captura ante fallas de red — resultados generados

_Generado por `scripts/prueba_red.py` el 2026-10-13 18:10 (UTC), Chromium 141.0.7390.37, 2.3 min. No editar a mano: la interpretación está en `prueba_red.md`._

## Corte prolongado

| Verificación | Resultado |
|---|---|
| Corte de red simulado | 27.9 s (los POST a `/events` se abortan) |
| Intervalos entre intentos (s) | 5.0, 9.4, 18.1, 44.0 |
| Esperado con backoff (s, ±20 %) | 5, 10, 20, 40 |
| Backoff dentro de la banda | sí |
| Mensaje al estudiante sin conexión | «sin conexión — 3 lote(s) pendientes, reintentando en 44 s. Podés seguir escribiendo: los registros se guardan en este navegador hasta reconectar.» |
| Pulsaciones tipeadas / guardadas | 80 / 80 (ninguna perdida) |
| Resincronización tras volver la red | 44.2 s |
| Eventos de estado guardados | [{"type": "sync_failure", "t": 10040.0, "failed_attempts": 3, "duration_ms": 71429}] |
| Indicadores | captura_incompleta |
| Requiere revisión | no |
| **Conforme** | **sí** |

## Buffer lleno

| Verificación | Resultado |
|---|---|
| Eventos generados sin conexión | 25000 (capacidad del buffer: 20000) |
| Pulsaciones guardadas / descartadas registradas | 20039 / 5001 |
| Guardadas + descartadas = capturadas | sí |
| Eventos de estado guardados | [{"type": "buffer_overflow", "t": 10295.0, "dropped": 5001, "from_t": 10295, "to_t": 10303}] |
| Indicadores | captura_incompleta |
| **Conforme** | **sí** |

## Reconexión avisada por el navegador

| Verificación | Resultado |
|---|---|
| Resincronización tras el evento `online` | 0.1 s (sin el aviso: próximo intento a los ~10 s) |
| Pulsaciones tipeadas / guardadas | 80 / 80 |
| Eventos de estado guardados | ninguno (corte breve: no es una falla persistente) |
| Indicadores | — |
| **Conforme** | **sí** |
