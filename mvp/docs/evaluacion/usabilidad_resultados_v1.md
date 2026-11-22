# Evaluación de usabilidad y navegabilidad del MVP: resultados (corrida 1, antes de las correcciones)

> **Versión archivada.** Corrida del 21/10/2026, previa a las correcciones del Incremento 16. Las métricas en bruto de esta corrida están en `docs/evaluacion/usabilidad/metricas_v1.json`. Las PNG citadas abajo se regeneraron en la corrida 2 (mismos nombres) y ya no muestran esta versión de la interfaz. La corrida vigente y la comparación «Antes / después» están en `usabilidad_resultados.md`.

**Tipo de evaluación.** Evaluación experta y automatizada de usabilidad y navegabilidad (inspección heurística + recorridos instrumentados). La hizo el equipo con agentes automatizados, el 21/10/2026, sobre el build de producción del dashboard (`vite preview`), con backend FastAPI y una base SQLite temporal propia.

**Qué no es.** No es una prueba con usuarios. No hubo participantes, ni SUS, ni opiniones, y **no reemplaza** una prueba con docentes y estudiantes. Los tiempos son de la automatización, no de una persona. Las 25 sesiones `SINT-*` son sintéticas (`seed_demo`). El valor de la evaluación está en detectar problemas antes de esa prueba con usuarios.

**Reproducir** (desde `mvp/`, alrededor de 3 min). axe-core se instala fuera del repo:

```bash
mkdir -p /tmp/axe && (cd /tmp/axe && npm install axe-core@4.10.2)
python scripts/evaluar_usabilidad.py --backend-python backend/.venv/bin/python \
    --axe /tmp/axe/node_modules/axe-core/axe.min.js   # puertos 8100 (API) y 5180 (web)
```

**Salidas**
- Capturas y métricas en bruto: `docs/evaluacion/usabilidad/`. Contiene `metricas.json` y 50 PNG. Las capturas de pantalla completa van numeradas `NN_<pantalla>_{desktop,mobile}.png`. Las demás son evidencias puntuales: `nav_*`, `p_*`, `e*_`, `t*_`.
- Entorno: Chromium (Playwright). Escritorio 1366×768, móvil 375×667. axe-core 4.10 con las etiquetas `wcag2a`, `wcag2aa`, `wcag21a` y `wcag21aa`.

## 1. Tareas

**Cómo se cuentan las acciones**
- Cuentan los clics, los envíos con Enter o Espacio, el botón Atrás y abrir una URL. Tipear caracteres no cuenta.
- El **mínimo** es el camino óptimo según la interfaz.
- En modo teclado, Tab y Shift+Tab se informan aparte. Se cuentan desde el principio de la página.
- **Red fallida**: requests fallidos y respuestas ≥ 400.

| Tarea | Resultado | Acciones (mín.) | Rutas | Tiempo autom. | Consola / red | Teclado: resultado · Tab |
|---|---|---|---|---|---|---|
| T1 Iniciar sesión | éxito | 2 (2) | 1 | 0,7 s | 0 / 0 | éxito · 1 |
| T2 Crear evaluación con política | éxito | 8 (8) | 1 | 4,8 s | 0 / 0 | éxito · 17 |
| T3 Encontrar el código para compartir | éxito con problemas | 0 (0) | 1 | 0,1 s | 0 / 0 | n/a |
| T4 Localizar sesiones a revisar | éxito | 2 (2) | 2 | 4,8 s | 0 / 0 | éxito · 7 |
| T5 Abrir detalle y entender indicadores | éxito con problemas | 1 (1) | 2 | 0,3 s | 0 / 0 | éxito · 10 |
| T6 Registrar decisión de revisión | éxito | 3 (1) | 1 | 1,3 s | 0 / 0 | éxito · 8 |
| T7 Cerrar evaluación y ver análisis poblacional | éxito con problemas | 3 (3) | 2 | 1,7 s | 0 / 0 | éxito · 8 (foco perdido) |
| T8 Leer el panorama | éxito | 1 (1) | 1 | 0,3 s | 0 / 0 | éxito · 9 |
| T9 Eliminar una sesión (RF17) | éxito con problemas | 3 (3) | 3 | 2,2 s | 0 / 1¹ | éxito · 9 (foco perdido) |
| E1 Ingresar con el código | éxito con problemas² | 2 (1) | 2 | 3,0 s | 1 / 1³ | n/a |
| E2 Información y consentimiento | éxito | 2 (2) | 1 | 0,5 s | 0 / 0 | éxito · 2 |
| E3 Escribir y entregar | éxito | 2 (2) | 1 | 14,2 s⁴ | 0 / 0 | éxito · 2 |
| E4 Entregar con corte de red y reintentar | éxito | 3 (2) | 1 | 22,3 s⁵ | 5 / 5 (esperados) | n/a |

**Notas de la tabla**
1. Un GET `/sessions/:id` abortado al salir de la página después de borrar.
2. Con **solo el código** la tarea queda bloqueada: la raíz lleva al login docente y no hay campo para ingresarlo. Solo funciona con el enlace completo `/exam/CODIGO`.
3. 404 esperado al probar un código inexistente.
4. Incluye el tecleo simulado de la respuesta.
5. Incluye los reintentos de 1, 2 y 4 s de `TakeExam.tsx`.

**Resumen**
- Resultados: 23 de 23 ejecuciones completas (13 con mouse y 10 solo con teclado). 6 terminaron con problemas.
- No hubo errores de consola inesperados.

**Mensajes observados en E4**
- Sin red, mientras se escribe: «sin conexión — 1 lote(s) pendientes, reintentando en 11 s. Podés seguir escribiendo…».
- Al entregar: «Enviando los últimos registros…».
- Después: «No se pudieron enviar 90 registro(s)… Revisá la conexión y reintentá».
  - Se ofrecen **Reintentar la entrega** y **Entregar sin esos registros**.
  - Al reconectar y reintentar: «El servidor confirmó tu entrega».
- El flujo es correcto. Sin embargo, ningún mensaje usa `role=alert` ni `aria-live`, y el aviso de «sin conexión» es texto gris de 13 px.

## 2. Navegabilidad

**Mapa de rutas** (`App.tsx`)

| Ruta | Pantalla | Se llega desde |
|---|---|---|
| `/login` | Login docente | `*` y rutas protegidas sin sesión; «Cerrar sesión» |
| `/exams` | Evaluaciones (inicio) | marca, «Evaluaciones» (barra), `/`, `*`, después de iniciar sesión y **después de eliminar una sesión** |
| `/exams/:id/sessions` | Sesiones y Panorama (pestañas sin ruta propia) | «Ver sesiones →» en `/exams`; nombre de la evaluación en `/validaciones` |
| `/sessions/:id` | Detalle de sesión | «Ver detalle →» en Sesiones y en Validaciones |
| `/validaciones` | Validaciones pendientes | «Validaciones pendientes» (barra) |
| `/exam/:joinCode` | Examen del estudiante (consentimiento → consigna → entrega, todo en una ruta) | solo con el enlace completo; no hay ningún enlace interno |

**Profundidad desde el inicio** (`/exams`), en clics:

| Pantalla | Clics |
|---|---|
| Sesiones | 1 |
| Validaciones | 1 |
| Detalle | 2 |
| Panorama | 2 |

**Desde el detalle de sesión no hay ninguna salida propia**
- No hay enlace a la evaluación ni migas de pan. Ningún ítem de la barra queda activo.
- Para volver a la evaluación hay que usar Atrás (1 acción) o la barra (2 acciones).

| Prueba | Resultado |
|---|---|
| Atrás: Detalle → Sesiones | Vuelve a Sesiones, pero **se pierde el filtro** «Solo sesiones que requieren revisión». |
| Atrás después de pasar a la pestaña Panorama | **Sale de la evaluación** hacia `/exams`: la pestaña no queda en el historial. |
| Atrás inmediatamente después del login | Muestra el formulario de login aunque hay sesión iniciada (`nav_atras_tras_login.png`). |
| Recargar `/exams`, `/`, `/exams/:id/sessions`, `/sessions/:id`, `/validaciones`, `/exam/:code` | Todas cargan bien con un enlace directo y después de recargar. |
| Recargar en la pestaña Panorama | Vuelve a «Sesiones». |
| **Recargar o salir y volver durante el examen** | Vuelve al consentimiento. **La respuesta escrita se pierde**, no hay aviso `beforeunload`, y al reingresar con el mismo código se crea una **segunda sesión** (`p_recarga_durante_examen.png`). |
| Enlace directo sin sesión iniciada | Redirige a `/login`, pero **después del login va a `/exams`, no al enlace pedido**. |
| Token vencido o inválido | No redirige al login: muestra «No se pudieron cargar las evaluaciones.» (`nav_token_invalido.png`). |
| `/ruta-inexistente` | Redirección silenciosa a `/exams` o `/login`, sin página 404. |
| `/exam` sin código (estudiante) | Termina en el **login docente** (`nav_404_exam_estudiante_sin_c_digo.png`). |
| `/exams/{id inexistente}/sessions` | Muestra «Sesiones / No hay sesiones todavía» y la pestaña Panorama, en lugar de un error (`nav_404_exams_inexistente_sessions.png`). |
| `/sessions/{id inexistente}` y `/exam/NOEXISTE` | Muestran un mensaje explícito («No se pudo cargar la sesión», «Código no encontrado»). |
| Estado activo de la barra | Activo en `/exams`, Sesiones y `/validaciones`, con `aria-current=page`. En el **detalle de sesión no hay ítem activo**. |
| Pestañas | Tienen `role=tab` y `aria-selected`, pero falta `aria-controls`/`tabpanel` y no responden a las flechas. |
| Título del documento | Siempre «ImprontIA»: no cambia por pantalla (WCAG 2.4.2). |
| Gestión del foco | Después de una navegación interna, abrir una confirmación o entregar, el foco queda en `<body>`. |

## 3. Métricas de interfaz por pantalla

**Cómo leer la tabla**
- Desborde: ancho del documento a 375 px. Si es mayor que 375, hay scroll horizontal.
- «< 24 px»: objetivos táctiles más chicos que 24 px. Se informan como «chicos / interactivos».
- «Altura»: alto de la página a 1366×768.
- INFLESZ: índice de legibilidad (Szigriszt-Pazos), calculado sobre los bloques de prosa con un conteo de sílabas aproximado.

| Pantalla (captura escritorio) | Contraste (nodos) | Desborde 375 px | Fuente mín. (textos < 12 px) | < 24 px | Altura | INFLESZ (bloque más largo) | CLS |
|---|---|---|---|---|---|---|---|
| Login (`01`) | 1 | no | 13 px (0) | 0/3 | 768 | – | 0 |
| Evaluaciones (`09`) | 2 | **447 px** | 11 (3) | 3/6 | 768 | – | 0 |
| Nueva evaluación (`05`) | 3 | 394 | 11 (2) | **10/17** | 975 | 75,6 bastante fácil (23 palabras) | 0 |
| Evaluación creada (`07`) | 2 | 447 | 11 (3) | 4/7 | 768 | 49,0 algo difícil | 0 |
| Sesiones, abierta (`21`) | 1 | **879 px** | 11 (**65**) | 4/36 | **2400** | 62,1 normal (47) | 0 |
| Sesiones, cerrada (`31`) | 1 | 889 | 11 (66) | 4/35 | 2348 | 56,4 normal | 0,002 |
| Panorama (`33`) | 1 | 394 | 11 (9) | 4/8 | 1865 | 60,4 normal (40) | 0,04 |
| Detalle de sesión (`25`, `27`) | 1 | 394 | 11 (3–4) | 4/9 | **1924–2049** | 54–57 algo difícil / normal (51) | 0 |
| Validaciones (`29`) | 1 | 598 | 11 (5) | 3/6 | 768 | 58,3 normal (41) | 0 |
| Estudiante: consentimiento (`13`) | 1 | no | 11 (1) | 1/3 (casilla de 13×13) | 768 (856 en móvil) | 72,9 bastante fácil, **un bloque de 150 palabras** | 0 |
| Estudiante: rindiendo (`15`) | 1 | no | 13 (0) | 0/2 | 768 | 58,9 normal | 0 |
| Estudiante: entrega fallida (`19`) / entregado (`17`) / código inexistente (`11`) | 1 / 0 / 0 | no | 13 | 0 | 768 | 66–74 | 0 |

**Carga** (mediana de 3 cargas en frío, localhost, build de producción)
- DOMContentLoaded: 69–106 ms. LCP: 120–316 ms según la corrida (los valores más altos son en Sesiones y Detalle). CLS ≤ 0,04.
- Según los umbrales de Core Web Vitals (LCP < 2,5 s y CLS < 0,1), el rendimiento no es un problema. Hay que tener en cuenta que es una red local.

**Posición de los controles clave en escritorio** (coordenada y)

| Control | Posición |
|---|---|
| Primera fila de sesiones | 836 px, por debajo del primer viewport |
| «Cerrar la evaluación…» | 656 px |
| Botón de decisión de revisión | 1644 px |
| «Eliminar esta sesión…» | 1698 px |

**Etiquetas y fuentes**
- Todos los campos tienen etiqueta (0 sin etiqueta).
- No se marcan los campos obligatorios.
- La validación de campos vacíos es la del navegador, que en este Chromium aparece en inglés: «Please fill out this field.».
- Hay textos de 11 px en encabezados de tabla, badges, pistas y legends.

**Consistencia y terminología**
- «Cerrar» tiene tres significados:
  - «Cerrar sesión»: logout.
  - «Cerrar la evaluación y analizar…».
  - «cerrar»: descartar un aviso, en minúscula.
- «Sesión» se usa a la vez para la sesión del docente y la sesión de examen del estudiante.
- El mismo estilo `btn-warning` sirve para «Requiere validación adicional» (no destructiva) y para «Confirmar la eliminación» (destructiva e irreversible).
- El tipo de sesión aparece crudo y en inglés: «exam».
- La evidencia del detalle muestra nombres internos, por ejemplo `paste_chars_total = 264 (umbral de referencia: 200)`.
- El nombre accesible del ítem de la barra se lee «Validaciones pendientes1».

## 4. Accesibilidad (axe-core, WCAG 2.1 A/AA)

**Resumen**

| Impacto | Reglas × pantalla | Nodos |
|---|---|---|
| Crítico | 0 | 0 |
| Serio | 15 | 20 |
| Moderado | 0 | 0 |
| Menor | 0 | 0 |

**Las 15 violaciones son de `color-contrast` (1.4.3)**
- Texto blanco sobre `--primary #6366f1` (`.btn-primary`): **4,46:1**.
- «IA» de la marca sobre el fondo: **4,22:1**.
- El mínimo es 4,5:1.

**Otros hallazgos**
- Buenas prácticas (axe, fuera de WCAG): falta un `<main>`/landmark en el login y en todas las pantallas del estudiante; no hay `h1` en el panel docente; hay `<th>` vacíos en las tablas.
- Hallazgos manuales sobre WCAG:
  - 2.4.2: el título no cambia por pantalla.
  - 4.1.3: los mensajes de estado no se anuncian (sin `aria-live`).
  - 2.5.8 (AA de WCAG 2.2, informativo): objetivos de 13–16 px.
  - 1.4.10: desborde horizontal a 320–375 px.
- Teclado:
  - Las 10 tareas se pudieron completar solo con teclado.
  - En los recorridos de foco, el **foco fue visible** en las 87 paradas (anillo por defecto del navegador; el CSS no define `:focus-visible`).
  - Problemas: el foco no se gestiona en las navegaciones, al abrir confirmaciones ni al entregar; las pestañas no usan flechas; la tabla de Sesiones tiene 36 paradas de foco antes de terminar.

## 5. Inspección heurística (Nielsen)

Escala de severidad: 0 = no es un problema, 1 = cosmético, 2 = menor, 3 = mayor, 4 = catastrófico.

| # | Heurística | Hallazgo (evidencia) | Sev. |
|---|---|---|---|
| H1 | Visibilidad del estado del sistema | Después de cerrar la evaluación, la tarjeta solo informa la fecha y no el resultado del modelo (`31_sesiones_cerrada_desktop.png`). El contador «Validaciones pendientes» no se actualiza después de registrar una revisión (`t6_revision_registrada.png`). El aviso de «sin conexión» es texto gris (`e4_sin_conexion_escribiendo.png`). La lista de evaluaciones no indica si una evaluación está cerrada. | 2 |
| H2 | Coincidencia con el mundo real | La evidencia muestra `paste_chars_total`, umbrales sin unidad y el tipo «exam» (`25_sesion_detalle_desktop.png`). Hay códigos de requerimientos («RF01», «RF04») en la interfaz docente (`05_crear_evaluacion_desktop.png`). | 2 |
| H3 | Control y libertad del usuario | Recargar o salir durante el examen pierde la respuesta y crea otra sesión (`p_recarga_durante_examen.png`). Atrás desde Panorama saca de la evaluación. Atrás pierde el filtro. Al eliminar una sesión se pierde el contexto (`t9_tras_eliminar.png`). | **4** (pérdida de la respuesta del estudiante) |
| H4 | Consistencia y estándares | «Cerrar» con tres significados; «sesión» ambigua; mismo estilo para una acción destructiva y una que no lo es; «cerrar» en minúscula; no hay página 404; el título es igual en todas las pantallas. | 2 |
| H5 | Prevención de errores | «Finalizar y entregar» entrega en un clic, sin confirmación. No hay guardado del borrador ni aviso `beforeunload`. Se puede reingresar con el mismo código y duplicar la sesión. No se marcan los campos obligatorios. | **3** |
| H6 | Reconocer antes que recordar | Fuera del aviso de creación no se muestra el enlace del estudiante ni hay botón de copiar (`09_evaluaciones_lista_desktop.png`). El estudiante necesita la URL exacta porque no hay pantalla «ingresá tu código» (`e1_raiz_sin_ingreso_por_codigo.png`). | **3** |
| H7 | Flexibilidad y eficiencia | Sin filtro, las sesiones a revisar no aparecen primero (orden por hora de inicio) y no se puede ordenar por columna. La tabla queda debajo de la política y del cierre (y = 836 px). Las pestañas y los filtros no quedan en la URL. | 2 |
| H8 | Diseño estético y minimalista | La pantalla de Sesiones mide 2400 px: la política completa y el texto del cierre preceden a la tabla (`21_sesiones_lista_desktop.png`). En el consentimiento hay un bloque de 150 palabras (`13_estudiante_consentimiento_desktop.png`). El detalle mide 2,5 viewports y la decisión está a 1644 px. | 2 |
| H9 | Ayudar a reconocer y recuperarse de errores | E4 resuelve bien el reintento con mensajes claros. Pero el token vencido muestra «No se pudieron cargar…» sin llevar al login (`nav_token_invalido.png`). Una evaluación inexistente aparece como «No hay sesiones todavía». `/exam` sin código lleva al login docente. La validación nativa aparece en inglés. | 2 |
| H10 | Ayuda y documentación | Hay ayudas contextuales correctas (callouts del panorama y de los indicadores, pistas en los campos). No hay una explicación breve de qué hacer con un indicador más allá del aviso. | 1 |

## 6. Problemas priorizados y propuesta de corrección

El esfuerzo es estimado: S < 2 h, M ≈ ½–1 día, L > 1 día.

| # | Sev. | Problema | Propuesta | Archivo / componente | Esf. |
|---|---|---|---|---|---|
| 1 | 4 | Recargar o salir durante el examen pierde la respuesta y duplica la sesión. | Guardar `sessionRef` (id y token) y el borrador de la respuesta en `sessionStorage` y retomar la sesión activa al volver. Agregar un aviso `beforeunload` mientras `phase === "active"`. En el backend, opcionalmente, devolver la sesión activa existente para el mismo código de participante. | `dashboard/src/pages/TakeExam.tsx` (+ `backend/app/routers/sessions.py` `/sessions/start`) | M |
| 2 | 3 | El estudiante no puede entrar solo con el código (la raíz y `/exam` llevan al login docente). | Agregar una ruta pública `/exam` (y un enlace «Soy estudiante» en `/login`) con un campo «Código de examen» que navegue a `/exam/:code`. | `App.tsx`, nueva página `pages/JoinExam.tsx`, `pages/Login.tsx` | S |
| 3 | 3 | Compartir el examen: solo se ve el código. El enlace es relativo y aparece únicamente en el aviso de creación, sin botón de copiar. | Mostrar la URL absoluta (`window.location.origin + /exam/CODE`) con un botón «Copiar enlace» en el aviso, en la lista y en la cabecera de la evaluación. | `pages/ExamsList.tsx`, `pages/SessionsList.tsx` | S |
| 4 | 3 | Entrega en un clic, sin confirmación. | Agregar un paso de confirmación en línea («¿Entregar? No vas a poder editar»), con el mismo patrón que «Confirmar el cierre». | `pages/TakeExam.tsx` | S |
| 5 | 3 | Eliminar una sesión navega a `/exams/{id}` (ruta inexistente) y termina en `/exams`, sin confirmación visible. | `navigate(\`/exams/${session.exam_id}/sessions\`, {state: {msg: "Sesión eliminada"}})` y mostrar el aviso en `SessionsList`. Usar un estilo «peligro» propio (`btn-danger`) para el botón de confirmación. | `pages/SessionDetail.tsx` (`deleteSession`), `pages/SessionsList.tsx`, `index.css` | S |
| 6 | 2 | En Sesiones, la tabla empieza a 836 px; sin filtro, las sesiones marcadas no van primero; el filtro y la pestaña se pierden con Atrás o al recargar. | Mover la política a un bloque colapsable (`<details>`) debajo de las pestañas. Ordenar con `needs_review` primero. Guardar el filtro y la pestaña en la query string (`?revision=1&tab=panorama`) con `useSearchParams`. | `pages/SessionsList.tsx`, `PolicyCard.tsx` | M |
| 7 | 2 | El detalle no tiene enlace de vuelta ni ítem activo; la decisión de revisión está a 1644 px. | Agregar «← {nombre de la evaluación}» en la cabecera, con la navegación marcando «Evaluaciones» como activa. Subir la tarjeta «Revisión docente» debajo de los indicadores y colapsar «Métricas calculadas». | `pages/SessionDetail.tsx`, `Layout.tsx` | S |
| 8 | 2 | El docente ve vocabulario técnico (`paste_chars_total`, «exam», «RF01»). | Usar `METRIC_LABELS` y unidades en `IndicatorEvidence` («Caracteres pegados: 264; referencia: 200»). Traducir `session_type`. Quitar los códigos RF de las etiquetas visibles. | `pages/SessionDetail.tsx`, `pages/ExamsList.tsx`, `PolicyCard.tsx`, `format.ts` | S |
| 9 | 2 | Desborde horizontal en móvil en todo el panel docente (barra superior de 394 px, tablas de 447–889 px). | Hacer que la barra superior haga `flex-wrap`. Envolver las tablas en `.table-wrap { overflow-x: auto }` o pasarlas a tarjetas por debajo de 600 px. Quitar el `width: 460` fijo del consentimiento a favor de `max-width`. | `index.css`, `Layout.tsx`, tablas en `pages/*` | M |
| 10 | 2 | Contraste por debajo de AA (4,46:1 y 4,22:1); textos de 11 px; objetivos de 13–16 px. | Usar `--primary: #5458e8` (o un texto más oscuro sobre el botón) y un `.brand span` más claro (#8b8ef5). Subir el mínimo a 12 px. Casillas de 18 px y padding vertical de 6 px en los enlaces de la barra. | `index.css` | S |
| 11 | 2 | Mensajes de estado sin anunciar; foco perdido en las navegaciones y confirmaciones; título fijo. | Agregar `role="status"`/`aria-live="polite"` en `sync-status` y en los avisos, y `role="alert"` en los errores. Enfocar el `h2` en cada cambio de ruta y el botón «Confirmar» al abrir una confirmación. Poner `document.title` por pantalla. | `TakeExam.tsx`, `SessionsList.tsx`, `SessionDetail.tsx`, `Layout.tsx` | M |
| 12 | 2 | El token vencido no lleva al login; el login no devuelve al enlace pedido; no hay 404; una evaluación inexistente aparece vacía. | En `request()`, ante un 401, borrar el token y redirigir a `/login?next=…`, y que `Login` navegue a `next`. Agregar una ruta `*` con una página «No encontrada» y enlaces útiles. Mostrar un error si falla `getExam`. | `api.ts`, `Layout.tsx` (`RequireAuth`), `pages/Login.tsx`, `App.tsx`, `pages/SessionsList.tsx` | M |
| 13 | 2 | Después del cierre no se ve el resultado; el contador de validaciones no se refresca; la lista no muestra el estado «Cerrada». | Mostrar en la tarjeta «El modelo marcó N de M sesiones · Ver panorama». Agregar una columna o badge «Cerrada» en `/exams`. Refrescar el contador después de `submitReview` (evento o contexto). | `pages/SessionsList.tsx`, `pages/ExamsList.tsx`, `Layout.tsx`, `pages/SessionDetail.tsx` | S |
| 14 | 1 | Terminología inconsistente («Cerrar» con tres sentidos, «sesión» ambigua). | Cambiar «Cerrar sesión» por «Salir», el «cerrar» del aviso por «✕ Ocultar» (con `aria-label`) y la marca de la barra por «Validaciones pendientes (1)». | `Layout.tsx`, `pages/ExamsList.tsx` | S |

**Siguiente paso.** Aplicar los puntos 1 a 5 y repetir este script. Después, hacer una prueba con 5 docentes y 5 estudiantes que incluya SUS y tiempos humanos, con el protocolo de `docs/evaluacion/protocolo_prueba_manual.md`.
