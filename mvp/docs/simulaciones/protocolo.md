# Protocolo de simulaciones de examen (Fase 2, P03)

**Para qué.** Martina y Juan rinden exámenes de prueba en el MVP desplegado, declarando en cada sesión una **condición simulada**. Con eso se obtienen las primeras sesiones humanas etiquetadas y se puede correr el mismo procedimiento de evaluación del Incremento 6 (FAR, FRR, AUC-ROC, AP, EER) sobre datos reales.

**Qué no es.** No es el piloto del cap. 18: son dos personas del equipo que conocen el sistema. Los resultados son **exploratorios** y se informan así. Sirven para ver si el procedimiento funciona con personas y qué señales responden a cada condición, no para afirmar el desempeño del sistema.

> Este protocolo lo validan Martina y Juan antes de empezar. Lo que está marcado como "a decidir" tiene un valor por defecto que se puede cambiar.

## 1. Preparación (una vez)

1. Desplegar el MVP (`docs/despliegue.md`): Render o Docker Compose. Los dos tienen que poder entrar desde su computadora.
2. Uno de los dos crea, como docente, **una evaluación** "Simulaciones ImprontIA":
   - Consigna con **4 a 6 preguntas de respuesta abierta**, para 20 a 30 minutos. Siempre la misma plantilla. Por ahora la consigna va completa en un solo texto. Cuando exista P04 (varias consignas por examen), se pasa a una pregunta por ítem.
   - Señales habilitadas: **todas** (teclado, mouse, foco y portapapeles).
   - Reglas del examen: **sin** "permite pegado" ni "permite otras pestañas". Así las reglas se aplican igual en todas las sesiones.
   - Retención: a decidir. Por defecto, sin plazo hasta terminar el análisis.
3. Cada persona usa **siempre el mismo código de participante** (seudónimo), por ejemplo `SIM-M` y `SIM-J`. Nunca nombre ni legajo.
4. El enlace de rendición lleva **`?simulacion=1`**:
   `https://<dashboard>/exam/<CÓDIGO>?simulacion=1`
   Con ese parámetro, la pantalla de inicio muestra el selector **"Condición de esta simulación"**. Sin el parámetro, el selector no aparece y la sesión queda sin etiqueta, como cualquier sesión real.

## 2. Condiciones

La condición se elige **al iniciar** la sesión. Se guarda en `sessions.condicion_simulacion`. El docente **no la ve**: no aparece en el listado, el detalle, el panorama ni ninguna respuesta de la API. El pipeline tampoco la lee. Solo sale por `scripts/exportar_sesiones.py`.

| Condición | Qué hacer | Señales que debería mover |
|---|---|---|
| `normal` | Rendir de verdad, sin ayuda. | Ninguna: es la línea base. |
| `pegado` | Copiar y pegar parte de la respuesta desde otra fuente (un documento propio o una web). | Volumen de pegado (regla). |
| `transcripcion` | Tipear una respuesta escrita de antemano, leyéndola de otra ventana o de papel, **sin pegar**. | Ritmo de tecleo uniforme (regla); cambios de foco si se lee en otra ventana. |
| `consulta_externa` | Buscar en otra pestaña o consultar una IA, volver y elaborar la respuesta. | Cambios de pestaña y tiempo fuera (reglas); pausas. |
| `suplantacion` | **Juan rinde con el código de Martina y viceversa**, de forma natural. | Ritmo de tecleo y mouse distinto al de la persona (modelo). Es la condición más valiosa: es lo que la biometría conductual debería poder detectar. |

En `suplantacion`, el código usado es el de la **otra** persona. Así la sesión queda asociada al participante suplantado, que es lo que pasaría en un caso real.

## 3. Volumen y orden

- **`normal`: al menos 10 sesiones por persona.** Son 20 o más en total, porque el modelo necesita **al menos 21 normales** para puntuar cada sesión sin usarla en su propio entrenamiento.
- **Cada condición anómala: 3 a 5 sesiones por persona.**
- Total esperado: **50 a 60 sesiones**.
- Las primeras 3 o 4 sesiones de cada persona son **normales** (familiarización). Después, el orden de las condiciones se **contrabalancea**: cada uno sigue una secuencia distinta, sorteada de antemano y anotada en la planilla. Por ejemplo, M: N-P-N-C-T-N-S…; J: N-S-N-T-C-N-P…
- Las sesiones se reparten en **varios días**, como máximo 3 o 4 por persona y por día, para que la línea base no sea de un solo momento.
- Se usa la misma computadora y el mismo navegador de siempre. Si alguna sesión se hace en otro equipo (por ejemplo, una notebook con touchpad), se anota en la planilla.

## 4. Durante la sesión

- Elegir la condición **antes** de "Comenzar" y verificar que sea la correcta. Si te equivocaste, terminá la sesión y anotala como inválida en la planilla; no se puede corregir desde la interfaz.
- Rendir la plantilla completa y **Finalizar**. Una sesión sin finalizar no se procesa ni se exporta.
- No mirar el detalle docente de tus propias sesiones hasta terminar la recolección. Ver qué marcó el sistema puede cambiar cómo rendís las siguientes.

**Planilla de campo** (compartida, fuera del sistema). Una fila por sesión con fecha, persona, código usado, condición, equipo, "válida sí/no" y observaciones. Sirve para controlar el orden y excluir sesiones inválidas. **No** se sube al repositorio.

## 5. Exportar y analizar

Desde `mvp/backend`, con la `DATABASE_URL` del despliegue. En Render es la "External Database URL" de la base:

```bash
# 1) Exportar (CSV sin datos personales; solo sesiones finalizadas con condición)
DATABASE_URL=postgres://... python -m scripts.exportar_sesiones --evaluacion <CÓDIGO> --salida simulaciones.csv

# 2) Analizar (imprime el reporte; con --salida guarda .md y .json)
python -m scripts.analizar_reales simulaciones.csv --salida ../docs/simulaciones/resultados

# 3) Variante con partición por participante (cuando haya ≥ 21 normales por persona)
python -m scripts.analizar_reales simulaciones.csv --excluir-participante
```

**Qué contiene el CSV.**
- Alias de sesión, evaluación y participante (`S001`, `E01`, `P01`), que no se pueden revertir desde el archivo.
- Orden de la sesión dentro de cada participante.
- Condición y `y_true` (1 = condición distinta de `normal`).
- Lo que el sistema marcó al finalizar: `marcada` ("requiere revisión"), `marcada_reglas`, `marcada_modelo` e `indicadores`.
- Cantidad de eventos, duración y las métricas de sesión completa.

**Qué no contiene:** códigos de participante, fechas, contexto, consignas, eventos crudos ni revisiones. Las sesiones a excluir según la planilla se borran del CSV antes de analizar.

**Qué calcula `analizar_reales.py`** (con las funciones de `app/evaluation/metrics.py`, la misma convención: positiva = condición anómala, FAR = anomalías no detectadas, FRR = falsas alarmas):

1. **Operación:** FAR y FRR de lo que el sistema marcó **en el momento**. Las primeras sesiones de la evaluación no tienen modelo (población < 20), así que en esas solo actúan las reglas. Eso también forma parte del resultado.
2. **Modelo, fuera de línea:** cada sesión se puntúa con un Isolation Forest (mismo `fit_population_model`, sin cambios) entrenado **solo con sesiones `normal` y sin la sesión evaluada**. Con eso salen AUC-ROC, AP y EER globales y por condición. Con `--excluir-participante`, el entrenamiento excluye todas las sesiones de la misma persona (partición por participante, cap. 18).
3. **Por condición:** cada condición contra las normales, con cuántas detectaron la operación, las reglas y el modelo.
4. **Intervalos 95 %** remuestreando **participantes** (1 000 remuestreos, semilla 2026). Con 2 participantes **no son interpretables**, y el reporte lo avisa.

## 6. Cómo informar los resultados

- Siempre como **simulaciones exploratorias del equipo (n = 2 personas)**, separadas de los resultados sintéticos del Incremento 6 y del piloto propuesto en el cap. 18.
- Informar el conteo por condición, las detecciones por condición y las métricas con sus avisos. No extrapolar a estudiantes reales.
- Lo esperable, según el diseño y los resultados sintéticos: las reglas detectan `pegado`, `consulta_externa` y, en parte, `transcripcion`, y el modelo poblacional aporta sobre todo en `suplantacion`. Si no pasa, es un hallazgo y se informa igual.

## 7. Privacidad

- Son datos de los propios autores, con consentimiento informado en la pantalla de inicio de cada sesión.
- El CSV no tiene datos personales. La base del despliegue sí tiene los eventos crudos (sin texto ni teclas) y los seudónimos.
- Al terminar el análisis, borrar la base del despliegue o aplicar la purga por retención (P05).
