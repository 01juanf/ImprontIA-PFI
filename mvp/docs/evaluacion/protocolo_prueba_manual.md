# Protocolo de prueba manual (≈ 15 min)

Complemento de la prueba interna automatizada (`scripts/prueba_interna.py`,
Incremento 9). Sirve para que Martina o Juan repitan **a mano** los cuatro
escenarios sobre el sistema real y, sobre todo, para cubrir lo que la
automatización no puede: un **cambio de pestaña real** del navegador (en la
prueba automatizada se simula, porque Playwright fija la página como visible).

No es un piloto: lo ejecutan los autores, sobre sí mismos, con datos de
prueba. Los resultados se registran como verificación de funcionamiento, no
como desempeño de detección (D03).

---

## 1. Preparación (≈ 3 min)

Desde `mvp/` (ver `README.md` para la instalación):

```bash
# Terminal 1 — backend (Python 3.11/3.12)
cd backend
python -m scripts.seed_teacher docente@uade.edu.ar 1234
uvicorn app.main:app --port 8010

# Terminal 2 — dashboard
cd dashboard
npm run dev            # http://localhost:5173
```

1. Entrar a `http://localhost:5173/login` con el docente creado.
2. **+ Nueva evaluación** → nombre "Prueba manual", cualquier texto en
   información/reglas/consigna, **todas las señales tildadas** → Crear.
   Anotar el código (ej. `A3F9C1`).
3. *(Opcional, para que también actúe el Isolation Forest)* cargar una
   línea base sintética en esa evaluación:
   `python -m scripts.seed_demo --join-code A3F9C1 --normales 24 --atipicas 0`
   (terminal 3, desde `backend/`). Sin este paso solo actúan las reglas, que
   es lo que verifica este protocolo.

Cada escenario se rinde en una pestaña nueva con
`http://localhost:5173/exam/<código>`, con el código de participante
indicado, tildando el consentimiento.

## 2. Escenarios (≈ 2–3 min cada uno)

| # | Participante | Qué hacer | Indicador de regla esperado |
|---|---|---|---|
| A | `PM-NORMAL` | Escribir la respuesta con naturalidad (3–4 renglones), mover el mouse con normalidad. Como mucho, salir una vez de la pestaña unos segundos. **Finalizar y entregar.** | Ninguno |
| B | `PM-PEGADO` | Escribir una frase. Copiar de otro documento un párrafo de **más de 200 caracteres** y pegarlo con Ctrl+V en la respuesta. Finalizar. | `Volumen de texto pegado alto` |
| C | `PM-FOCO` | Mientras se escribe, cambiar **7 veces a otra pestaña del mismo navegador** (Ctrl+Tab o clic en otra pestaña) y volver a los pocos segundos. Finalizar. | `Cambios de pestaña frecuentes` (y además `Pérdida de foco prolongada` si el tiempo total afuera supera 60 s) |
| D | `PM-TRANSCRIPCION` | Copiar a mano, a ritmo parejo, un texto impreso o en otra pantalla. Finalizar. | Probablemente **ninguno** (ver nota) |

**Notas importantes**

- **Escenario C — cambiar de pestaña, no de ventana.** El pipeline cuenta
  como "cambio de pestaña" el evento de visibilidad `hidden`, que el
  navegador emite al pasar a otra pestaña o minimizar la ventana. Cambiar a
  **otra aplicación con Alt+Tab dejando visible el navegador** solo produce
  una pérdida de foco de la ventana (`window_blur`), que `capture.ts`
  registra pero que hoy **no** alimenta ningún indicador. Si se hace así, es
  esperable que el escenario C no dispare el indicador: anotarlo como
  observación (es una limitación conocida del MVP, no un error de la prueba).
- **Escenario D.** La regla `ritmo_tecleo_atipico` busca una variabilidad de
  pulsación inferior a 5 ms, propia de texto inyectado por un programa (lo
  que reproduce la prueba automatizada con un ritmo constante). Una persona
  que transcribe, aunque escriba parejo, difícilmente baje de ese umbral.
  Que D no genere indicadores es el resultado esperable y muestra el límite
  de la señal: la dinámica de tecleo por sí sola no distingue una
  transcripción humana de una redacción propia.
- El indicador del modelo poblacional (`Patrón atípico frente a la línea
  base poblacional`) puede aparecer en cualquier escenario si se cargó la
  línea base sintética: el movimiento de mouse y el ritmo de una persona
  real difieren de los del generador sintético (ver bitácora, Incremento
  7). Registrarlo, pero no forma parte de lo esperado.

## 3. Verificación (≈ 3 min)

En el dashboard: **Evaluaciones → Ver sesiones** de "Prueba manual". Para
cada sesión `PM-*`, abrir **Ver detalle** y anotar los indicadores que
muestra. Comprobar además, en "Métricas calculadas":

- B: `Caracteres pegados (total)` ≈ largo del párrafo pegado (solo el número;
  el texto no se guarda).
- C: `Cambios de pestaña` = cantidad de salidas realizadas.

*(Opcional, privacidad)* Con el backend en SQLite, verificar que los eventos
no contienen texto:
`sqlite3 backend/impronta.db "select type, payload from events limit 30;"` →
solo deben verse códigos de tecla (`KeyA`…), coordenadas, estados de
visibilidad y cantidades de caracteres.

## 4. Registro de resultados

Copiar esta tabla en la bitácora (o en `prueba_interna.md`, sección
"Prueba manual") con fecha y quién la ejecutó:

| Escenario | Participante | Indicadores mostrados | ¿Coincide con lo esperado? | Observaciones |
|---|---|---|---|---|
| A normal | PM-NORMAL | | | |
| B pegado | PM-PEGADO | | | |
| C cambios de foco | PM-FOCO | | | |
| D transcripción | PM-TRANSCRIPCION | | | |

Fecha: ____/10/2026 · Ejecutó: __________ · Navegador y versión: __________ ·
¿Se cargó línea base sintética? sí / no
