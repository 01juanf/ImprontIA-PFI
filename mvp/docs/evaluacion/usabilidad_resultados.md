# Evaluación de usabilidad y navegabilidad del MVP: resultados (corrida 2, después de las correcciones)

**Tipo de evaluación.** Evaluación experta y automatizada de usabilidad y navegabilidad (inspección heurística + recorridos instrumentados). La hizo el equipo con agentes automatizados, el 22/10/2026, sobre el build de producción del dashboard (`vite preview`), con backend FastAPI y una base SQLite temporal propia. Es la **segunda corrida** del mismo script, después de aplicar las correcciones propuestas en la corrida 1 (`usabilidad_resultados_v1.md`, métricas en `usabilidad/metricas_v1.json`).

**Qué no es.** No es una prueba con usuarios. No hubo participantes, ni SUS, ni opiniones, y **no reemplaza** una prueba con docentes y estudiantes. Los tiempos son de la automatización, no de una persona. Las sesiones `SINT-*` son sintéticas (`seed_demo`). El valor de la evaluación está en detectar problemas antes de esa prueba con usuarios.

**Reproducir** (desde `mvp/`, alrededor de 4 min). axe-core se instala fuera del repo:

```bash
mkdir -p /tmp/axe && (cd /tmp/axe && npm install axe-core@4.10.2)
python scripts/evaluar_usabilidad.py --backend-python backend/.venv/bin/python \
    --axe /tmp/axe/node_modules/axe-core/axe.min.js   # puertos 8100 (API) y 5180 (web)
```

También se corre con `scripts/reproducir.sh --usabilidad --axe …`.

**Salidas**
- Capturas y métricas en bruto: `docs/evaluacion/usabilidad/` (`metricas.json` y 48 PNG; la corrida 1 dejó 49, la diferencia es `e1_raiz_sin_ingreso_por_codigo.png`, que ya no aplica). Las PNG de la corrida 1 se sobrescribieron: sus métricas siguen en `metricas_v1.json`.
- Entorno: Chromium (Playwright). Escritorio 1366×768, móvil 375×667. axe-core 4.10.2 con las etiquetas `wcag2a`, `wcag2aa`, `wcag21a` y `wcag21aa`.

**Cambios en el script entre corridas** (la lógica de medición es la misma):
- La casilla del filtro de Sesiones ahora vive en la URL (`?revision=1`) y se actualiza después de la navegación; `Locator.set_checked` la daba por no cambiada. El script hace un clic (una acción, como antes) y espera el estado final.
- T7 y T9 (teclado) tenían el estado «éxito con problemas» fijo en el código; ahora se decide con lo medido (resultado del modelo visible en la tarjeta de cierre; foco al abrir la confirmación). T7 agrega una observación si el botón de cierre queda fuera del primer viewport.
- El mapa de rutas declarado se actualizó a `App.tsx` (`/rendir`, `/exam`, `/exams/:id`, página 404).

## Antes / después

| Medida | Corrida 1 (21/10) | Corrida 2 (22/10) |
|---|---|---|
| Tareas completadas | 23 de 23 | 23 de 23 |
| Tareas «éxito con problemas» | **6** (T3, E1, T5, T7, T9 con mouse; T9 con teclado) | **0** |
| Tareas con más acciones que el mínimo | 3: E1 2 (1), E4 3 (2), T6 3 (1) | 2: E4 4 (3), T6 3 (1) |
| axe (WCAG 2.1 A/AA): serias + críticas | **15** reglas × pantalla (20 nodos), todas `color-contrast` | **0** |
| Pantallas con desborde horizontal a 375 px | **11 de 17** (hasta 893 px) | **0 de 17** |
| Fuente mínima (textos < 12 px, suma de pantallas) | 11 px (174) | 12 px (0) |
| Objetivos < 24 px a 375 px (suma de pantallas) | 37 | 13 (todos casillas de 18×18 dentro de una etiqueta clicable) |
| Pérdida de foco (queda en `<body>`) | al abrir las confirmaciones de T7 y T9 (teclado) y tras el error de login | ninguna: el foco va a «Confirmar…» y, tras el error de login, al email |
| Foco visible en los recorridos con Tab | 87 de 87 paradas | 105 de 105 paradas |
| CLS máximo (pantallas / carga en frío) | 0,04 / 0,04 | 0,004 / 0 |
| Título del documento | siempre «ImprontIA» | uno por pantalla («Sesión de EST-USAB-01 · ImprontIA») |
| Severidades heurísticas H1–H10 | 2, 2, **4**, 2, **3**, **3**, 2, 2, 2, 1 | 1, 1, 0, 1, 0, 0, 2, 1, 0, 1 |

Los conteos de acciones de E1 y E3 cambiaron de forma deliberada: E1 ahora se resuelve **con solo el código** (raíz → «¿Sos estudiante?» → código → consentimiento, 3 acciones; con el enlace completo sigue bastando 1) y E3 suma el paso de confirmación de la entrega (2 → 3 acciones).

Durante la corrida 2 aparecieron y se corrigieron (con nueva corrida) tres problemas baratos: el desborde a 375 px seguía en las tablas porque los `.sr-only` de las celdas se posicionaban respecto de la página (`.table-wrap { position: relative }`); la pantalla de Sesiones desplazaba el diseño al cargar (CLS 0,54) porque la línea del código y la tabla llegaban después que las tarjetas de abajo; y las pestañas no respondían a las flechas. También se marcaron los campos obligatorios, el mensaje de validación quedó en castellano («Completá este campo.») y el botón «Cancelar» del formulario dejó de tener el estilo primario.

## 1. Tareas

**Cómo se cuentan las acciones**: clics, envíos con Enter o Espacio, el botón Atrás y abrir una URL; tipear caracteres no cuenta. El **mínimo** es el camino óptimo según la interfaz. En modo teclado, Tab y Shift+Tab se informan aparte. **Red fallida**: requests fallidos y respuestas ≥ 400.

| Tarea | Resultado | Acciones (mín.) | Tiempo autom. | Consola / red | Teclado: resultado · Tab |
|---|---|---|---|---|---|
| T1 Iniciar sesión | éxito | 2 (2) | 0,6 s | 0 / 0 | éxito · 1 |
| T2 Crear evaluación con política | éxito | 8 (8) | 4,0 s | 0 / 0 | éxito · 17 |
| T3 Encontrar el enlace para compartir | éxito | 0 (0) | 0,4 s | 0 / 0 | n/a |
| T4 Localizar sesiones a revisar | éxito | 2 (2) | 3,3 s | 0 / 0 | éxito · 11 |
| T5 Abrir detalle y entender indicadores | éxito | 1 (1) | 0,2 s | 0 / 0 | éxito · 11 |
| T6 Registrar decisión de revisión | éxito | 3 (1)¹ | 1,1 s | 0 / 0 | éxito · 10 |
| T7 Cerrar evaluación y ver análisis poblacional | éxito | 3 (3) | 1,0 s | 0 / 0 | éxito · 20 |
| T8 Leer el panorama | éxito | 1 (1) | 0,2 s | 0 / 0 | éxito · 9 |
| T9 Eliminar una sesión (RF17) | éxito | 3 (3) | 2,1 s | 0 / 1² | éxito · 19 |
| E1 Ingresar con el código | éxito | 3 (3) | 2,6 s | 1 / 1³ | n/a |
| E2 Información y consentimiento | éxito | 2 (2) | 0,4 s | 0 / 0 | éxito · 2 |
| E3 Escribir y entregar | éxito | 3 (3) | 13,3 s⁴ | 0 / 0 | éxito · 2 |
| E4 Entregar con corte de red y reintentar | éxito | 4 (3) | 21,2 s⁵ | 5 / 5 (esperados) | n/a |

1. Tildar un indicador y escribir una nota son opcionales: el mínimo cuenta solo la decisión.
2. El navegador registra el `DELETE /sessions/:id` como `net::ERR_ABORTED`, pero el servidor respondió 204, la sesión no existe después (404) y la app navegó a la evaluación con el aviso «Sesión de SINT-017 eliminada…». Es un artefacto del registro de red, no un fallo.
3. 404 esperado al probar un código inexistente.
4. Incluye el tecleo simulado de la respuesta.
5. Incluye los reintentos de 1, 2 y 4 s.

**Observaciones medidas**
- T2/T3: la confirmación y la lista muestran la URL absoluta del examen con «Copiar enlace» (confirmación «Copiado»).
- T4: la primera fila de Sesiones está en y = 346 px (antes 836) y, sin filtro, la sesión marcada aparece primera.
- T5: la evidencia se lee «Caracteres pegados: 264 · umbral de referencia: 200»; el tipo de sesión, «Examen»; hay enlace de vuelta a la evaluación.
- T6: la decisión está en y = 731 px (antes 1644) y el contador «Validaciones pendientes» se actualiza sin cambiar de ruta.
- T7: la tarjeta de cierre informa «El modelo marcó 3 de 27 sesiones evaluadas» y la lista muestra «Cerrada». **Pero** «Cerrar la evaluación y analizar…» quedó en y = 2077 px (antes 656), debajo de la tabla de 27 sesiones, y con teclado hacen falta 20 Tab (antes 8).
- E3: pide confirmación («Sí, entregar», con el foco en ese botón) y guarda el borrador.
- E4: el aviso de sin conexión está destacado y los mensajes de error se anuncian (`aria-live`).

## 2. Navegabilidad

| Prueba | Corrida 1 | Corrida 2 |
|---|---|---|
| Atrás: Detalle → Sesiones con filtro | pierde el filtro | **conserva el filtro** (el filtro está en la URL) |
| Atrás después de pasar a Panorama | sale a `/exams` | vuelve a la pestaña Sesiones de la evaluación |
| Atrás inmediatamente después del login | muestra el formulario de login | no vuelve al login (sale de la app: el login reemplaza la entrada del historial) |
| Recargar en Panorama | vuelve a Sesiones | queda en Panorama |
| Recargar o salir y volver durante el examen | pierde la respuesta y crea otra sesión | conserva la respuesta, avisa al salir (`beforeunload`) y retoma la misma sesión (1 sesión para ese código) |
| Enlace directo sin sesión iniciada | después del login va a `/exams` | vuelve al enlace pedido |
| Token vencido o inválido | «No se pudieron cargar…» | redirige al login |
| `/ruta-inexistente` (con y sin sesión) | redirección silenciosa | página «Página no encontrada» con enlaces |
| `/exams/{inexistente}/sessions` | «No hay sesiones todavía» | «Evaluación no encontrada» + volver |
| `/exam` sin código | login docente | formulario «Ingresar a un examen» |
| Ítem activo en el detalle de sesión | ninguno | «Evaluaciones», con migas «← {evaluación}» |
| Pestañas | sin `aria-controls`/`tabpanel`, sin flechas | `tablist`/`tab`/`tabpanel` con `aria-controls`; flechas, Inicio y Fin cambian de pestaña |

Profundidad desde el inicio sin cambios: Sesiones y Validaciones a 1 clic; Detalle y Panorama a 2. Todas las rutas cargan con enlace directo y después de recargar.

## 3. Métricas de interfaz por pantalla (corrida 2)

| Pantalla | Desborde 375 px | Fuente mín. | < 24 px (chicos / interactivos) | Altura 1366×768 | INFLESZ (bloque más largo, palabras) |
|---|---|---|---|---|---|
| Login | no | 12 px | 0/4 | 768 | – |
| Evaluaciones (vacía / lista / creada) | no | 12 | 0/6 · 0/8 · 0/10 | 888 | 49,8–50,0 (19–28) |
| Nueva evaluación | no | 12 | 7/18 (casillas) | 1303 | 70,1 (23) |
| Sesiones (abierta / filtro / cerrada) | no | 12 | 1/40 · 1/14 · 1/40 | 2554 · 1018 · 2537 | 65,6 / 56,1 |
| Panorama | no | 12 | 0/12 | 1966 | 61,0 (40) |
| Detalle de sesión (abierta / revisada) | no | 12 | 1/11 | 1513 · 1683 | 55,6 / 53,4 (51) |
| Validaciones | no | 12 | 0/6 | 888 | 58,3 (41) |
| Estudiante: consentimiento | no | 12 | 1/3 | 781 | 72,9, **bloque de 150 palabras** |
| Estudiante: rindiendo / entregado / entrega fallida / código inexistente | no | 12–13 | 0 | 768 | 65,9–74,3 |

La altura del panel docente es ahora al menos 888 px porque el pie con la versión queda siempre debajo del primer viewport (así no se desplaza al cargar). En las pantallas con tablas, a 375 px la tabla se desplaza dentro de su contenedor y la página no.

**Carga** (mediana de 3 cargas en frío, localhost, build de producción): DOMContentLoaded 42–54 ms; LCP 68–156 ms; CLS 0 en todas las cargas medidas.

## 4. Accesibilidad (axe-core, WCAG 2.1 A/AA)

| Impacto | Corrida 1: reglas × pantalla (nodos) | Corrida 2 |
|---|---|---|
| Crítico | 0 (0) | 0 (0) |
| Serio | 15 (20) | 0 (0) |
| Moderado | 0 (0) | 0 (0) |
| Menor | 0 (0) | 0 (0) |

Fuera de WCAG, axe sigue informando la buena práctica `page-has-heading-one` en las 11 pantallas del panel docente: el título de cada pantalla es un `h2`. Las pantallas del estudiante y el login ya tienen `main` y `h1`.

## 5. Inspección heurística (Nielsen)

Escala: 0 = no es un problema, 1 = cosmético, 2 = menor, 3 = mayor, 4 = catastrófico. Severidad asignada por el equipo a partir de lo medido.

| # | Heurística | Corrida 1 | Corrida 2 | Lo que queda (evidencia) |
|---|---|---|---|---|
| H1 | Visibilidad del estado del sistema | 2 | 1 | En la pestaña Panorama, la tarjeta de cierre sigue ofreciendo «Ver panorama» (`33_panorama_desktop.png`). |
| H2 | Coincidencia con el mundo real | 2 | 1 | En el contexto de las sesiones sintéticas se ve la clave cruda «ORIGEN: sintetico» (captura de la demo `11_detalle_atipico_modelo_poblacional.png`). Solo afecta a datos de demostración. |
| H3 | Control y libertad del usuario | **4** | 0 | — (recarga, Atrás, filtro y eliminación conservan el contexto). |
| H4 | Consistencia y estándares | 2 | 1 | Las pantallas docentes no tienen `h1` (el título es `h2`). |
| H5 | Prevención de errores | **3** | 0 | — (confirmación de entrega, borrador, `beforeunload`, una sola sesión por código, campos obligatorios marcados). |
| H6 | Reconocer antes que recordar | **3** | 0 | — (enlace absoluto + «Copiar enlace»; `/rendir` con el código). |
| H7 | Flexibilidad y eficiencia | 2 | 2 | Sin orden por columna; el cierre quedó a y = 2077 px y a 20 Tab, debajo de la tabla; en móvil «Ver sesiones →» queda fuera de la vista dentro de la tabla desplazable. |
| H8 | Diseño estético y minimalista | 2 | 1 | Bloque de 150 palabras en el consentimiento; Sesiones mide 2554 px con 27 sesiones. |
| H9 | Reconocer y recuperarse de errores | 2 | 0 | — (token vencido → login y vuelta al enlace; errores explícitos; foco al email tras un login fallido; validación en castellano). |
| H10 | Ayuda y documentación | 1 | 1 | Sin explicación breve de qué hacer con un indicador más allá del aviso. |

## 6. Problemas que quedan

| # | Sev. | Problema | Propuesta | Esf. |
|---|---|---|---|---|
| 1 | 2 | «Cerrar la evaluación y analizar…» quedó debajo de la tabla (y = 2077 px con 27 sesiones; 20 Tab). Es el costo de haber subido la tabla. | Repetir el botón de cierre (o un resumen «Abierta · Cerrar…») en la cabecera de la evaluación, junto al código. | S |
| 2 | 2 | En móvil, las tablas se desplazan dentro de su contenedor: la acción de cada fila («Ver sesiones →», «Ver detalle →») queda fuera de la vista. | Por debajo de 600 px, mostrar cada fila como tarjeta, o fijar la columna de acción. | M |
| 3 | 2 | No se puede ordenar la tabla de Sesiones por columna. | Encabezados con botón y `aria-sort` (al menos Inicio e Indicadores). | M |
| 4 | 1 | Las pantallas del panel docente no tienen `h1` (buena práctica de axe). | Pasar el título de cada pantalla a `h1` con la misma apariencia (hay que ajustar los selectores `h2` de los scripts de prueba). | S |
| 5 | 1 | Consentimiento con un bloque de 150 palabras. | Separar «Qué se registra» en viñetas cortas y dejar el detalle en un desplegable. | S |
| 6 | 1 | Casillas de 18×18 px (< 24 px), aunque la etiqueta completa es clicable. | Subir a 20–24 px si una prueba con usuarios lo muestra como problema. | S |
| 7 | 1 | «Ver panorama» visible estando ya en Panorama; clave cruda «sintetico» en el contexto. | Ocultar el enlace en esa pestaña; traducir las claves de contexto conocidas. | S |

**Siguiente paso.** Hacer la prueba con 5 docentes y 5 estudiantes, con SUS y tiempos humanos, con el protocolo de `docs/evaluacion/protocolo_prueba_manual.md`. Esta evaluación no la reemplaza.
