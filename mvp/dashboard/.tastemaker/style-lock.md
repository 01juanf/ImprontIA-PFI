# Style lock · ImprontIA (rediseño del panel, nov. 2026)

Skill usada: tastemaker (codeswithroh/tastemaker), modo build, track "app shell".
Escaneos: anti_slop_scan.py y audit_motion.py de la misma skill.

## Dirección (elegida por el equipo)
Híbrido. La marca vive en negro (#05070C) con el azul del logo (#4888F4): inicio, ingreso,
toda la experiencia del estudiante y la barra lateral del docente. Las superficies de trabajo
del docente (tablas, evidencia, revisión) van en "papel" (#F4F6FA / #FFFFFF), como el modo
paper del pitch: se leen mejor proyectadas y en revisiones largas.

Tesis de diseño: "evidencia para revisar, no veredictos". Cada pantalla muestra la evidencia
como algo para mirar (huella de señales, medidor contra umbral, desvíos frente a la cohorte),
con el texto como pie de foto. La decisión siempre queda visualmente del lado del docente
(panel de revisión fijo a la derecha).

## Tipografía
- Display: Poppins 500/600 (la del logotipo). Solo títulos y números grandes.
- Texto/UI: Instrument Sans (variable).
- Datos: IBM Plex Mono (códigos de examen, participantes, valores, etiquetas cortas).

## Color (contrato verificado con check_contrast.py)
Papel: ink #0B1220 · bg #F4F6FA · surface #FFFFFF · muted #5D6675 (5.4:1 sobre bg)
· accent #245FCB (5.4:1 sobre bg, texto/foco) · line #DFE4EC (decorativa)
Estados: warn #9A5212 sobre #FDF1E4 (5.3:1) · ok #0F7A58 sobre #E6F5EF (4.7:1)
· info #1F56C2 sobre #EAF1FE (5.8:1) · danger #B42318
Negro: texto #F4F6FA · muted #A7ADBB (8.6:1) · dim #8A93A6 (6.5:1) · brand #4888F4 (5.9:1)
· botón primario sobre negro: fill #4888F4 con texto #0B1220 (5.4:1)
Botón primario sobre papel: fill ink #0B1220, texto blanco (18.7:1). El azul de marca no se
usa como fill con texto blanco (3.3:1, no pasa).

## Ruptura intencional
La "huella" de cada sesión: una tira de cinco glifos (pegado, pestaña, foco, tecleo, modelo)
que reemplaza dos columnas de badges de texto. En el detalle, el número de la evidencia
aparece grande, fuera de la grilla de la tarjeta.

## Motion
App shell: entradas de 180-220 ms (opacity + translateY 6px), escalonado corto en listas,
diálogos nativos con fade. Nada de hover-scale. prefers-reduced-motion: solo opacidad.

## No hacer
Gradientes índigo/violeta, texto con gradiente, emoji como íconos, itálicas en títulos,
guiones largos en textos nuevos de la interfaz, métricas inventadas.
