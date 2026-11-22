# Prueba de resiliencia de la captura ante fallas de red (Incremento 10)

**Qué se verifica.** El cap. 15 ("Captura de señales") pide que el envío de
lotes tenga **reintentos con backoff**, un **buffer local acotado** y que el
**agotamiento del buffer o una falla persistente se registren como evento
propio, visible para la revisión docente**, de modo que una caída de
conectividad no interrumpa la evaluación ni descarte evidencia en silencio.
Hasta el Incremento 9 el MVP reintentaba cada 5 s fijos, sin límite de buffer
ni registro (desvío señalado en el cap. 17 §Limitaciones). El Incremento 10
lo implementó (`dashboard/src/syncQueue.ts`, `TakeExam.tsx`; en el backend,
`features.py::compute_capture_integrity` y el indicador informativo
`captura_incompleta`), y esta prueba lo verifica sobre el sistema real.

**Cómo.** `scripts/prueba_red.py` levanta backend + dashboard reales con una
base SQLite temporal y, con Playwright/Chromium, rinde tres sesiones desde la
vista del estudiante. La falla de red se simula de dos maneras: abortando los
`POST /sessions/{id}/events` (el navegador no se entera: solo fallan los
envíos, como en una red que "parece" conectada) y con el modo sin conexión
del navegador (dispara los eventos `offline`/`online`). Resultados generados:
`prueba_red_resultados.md` (tablas) y `prueba_red.json` (no se versiona);
con `--capturas DIR` guarda además `16_detalle_captura_incompleta.png`, el
detalle docente de la sesión con corte.

| Escenario | Qué hace | Qué se espera |
|---|---|---|
| `corte_prolongado` | El estudiante escribe 40 caracteres, se corta la red, escribe 40 más sin conexión y la red vuelve tras la 3.ª falla consecutiva. | Intentos espaciados 5 → 10 → 20 → 40 s (±20 % de variación aleatoria); las 80 pulsaciones llegan; se guarda un `sync_failure`; el docente ve `captura_incompleta` y la sesión **no** queda priorizada por eso. |
| `buffer_lleno` | Con la red cortada se generan 25 000 eventos de teclado (capacidad del buffer: 20 000). | Lo que no entra se cuenta y llega como `buffer_overflow`; eventos guardados + descartados = eventos capturados; aparece `captura_incompleta`. |
| `reconexion` | Corte breve avisado por el navegador. | Al volver la red se reintenta enseguida (sin esperar el próximo intento del backoff); un corte breve no deja registro de falla persistente. |

## Resultados (corrida del 13/10/2026, 18:10 UTC; detalle en `prueba_red_resultados.md`)

- **Backoff:** intervalos medidos 5,0 / 9,4 / 18,1 / 44,0 s frente a
  5 / 10 / 20 / 40 s esperados; todos dentro de la banda de ±20 %. En las
  tres corridas previas del mismo guion (durante el desarrollo): 5,0 / 9,9 /
  18,0 / 45,0 s; 5,0 / 10,8 / 23,2 / 45,8 s y 5,0 / 10,7 / 21,3 / 47,2 s,
  también dentro de la banda.
- **Sin pérdida:** 80 pulsaciones tipeadas, 80 guardadas. Lo escrito sin
  conexión quedó en el buffer del navegador y se envió al volver la red, en
  orden y sin duplicados (el número de lote permite al backend descartar un
  reenvío ya aplicado).
- **Registro de la falla persistente:** un evento
  `sync_failure {failed_attempts: 3, duration_ms: 71 429}` con la marca
  temporal de la primera falla. La sesión quedó con el indicador
  `captura_incompleta` (nivel bajo) y **sin** "Requiere revisión".
- **Buffer lleno:** 20 039 pulsaciones guardadas + 5 001 descartadas
  registradas = 25 040 capturadas. Los descartados superan en uno a los
  5 000 "de más" porque en el instante del corte el buffer todavía tenía un
  evento sin enviar (la última liberación de tecla); lo que importa es que
  la cuenta cierra: nada se perdió sin registro. (En la primera corrida el
  guion exigía exactamente 5 000 descartados y marcó el escenario como no
  conforme con 5 002 por la misma razón; se corrigió la verificación, no el
  código.)
- **Reconexión avisada:** resincronizó en 0,1 s tras el evento `online`
  (sin el aviso, el próximo intento habría llegado a los ~10 s), con todas
  las pulsaciones y sin evento de falla persistente.
- Mensaje que ve el estudiante sin conexión: «sin conexión — 3 lote(s)
  pendientes, reintentando en 44 s. Podés seguir escribiendo: los registros
  se guardan en este navegador hasta reconectar.»

## Decisiones tomadas a partir de la prueba y del diseño

1. **La captura incompleta no prioriza la sesión.** Una mala conexión no es
   un indicio sobre la conducta del estudiante: el indicador
   `captura_incompleta` es **informativo** (nivel bajo, `prioritizes_review =
   False`), se muestra en el detalle con su propio estilo y la leyenda "este
   aviso no prioriza la sesión para revisión", y le dice al docente que las
   métricas se calcularon sobre una evidencia parcial. Si la sesión además
   tiene un indicador que prioriza, se marca por ese otro.
2. **Al llenarse el buffer se conserva lo más antiguo** y se descarta lo
   nuevo, contando cuántos eventos y en qué rango temporal; los eventos de
   estado de la captura entran aunque el buffer esté lleno.
3. **Umbral de "falla persistente": 3 intentos consecutivos fallidos**
   (~35 s sin poder enviar). Cortes más breves se recuperan solos y no
   ensucian la evidencia con avisos.
4. **Reintento inmediato con el evento `online`**: el backoff protege al
   servidor cuando muchos estudiantes pierden la conexión a la vez (la
   variación aleatoria evita que reintenten sincronizados), pero no tiene
   sentido esperar hasta 60 s cuando el navegador ya sabe que volvió la red.
5. **Al finalizar, hasta 3 reintentos (1, 2 y 4 s)** antes de cerrar; si aun
   así quedan registros sin enviar, la pantalla final se lo dice al
   estudiante en lugar de confirmar "tu sesión fue registrada".

## Límites de la prueba

- La red se simula desde el navegador automatizado; no se probó una red
  móvil real ni la pérdida de conexión del propio backend.
- El buffer vive en memoria de la pestaña: si el estudiante cierra o recarga
  la pestaña sin conexión, lo pendiente se pierde (el intento final con
  `keepalive` no puede enviar sin red). Persistirlo en el almacenamiento del
  navegador queda como trabajo futuro, a evaluar junto con la política de
  retención (RNF10).
- Capacidad de 20 000 eventos: con teclado y mouse habilitados (~15 eventos
  por segundo) alcanza para unos 20 minutos sin conexión. Es un valor de
  diseño, no calibrado con sesiones reales.
