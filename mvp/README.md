# ImprontIA — MVP

Implementación del MVP de ImprontIA: captura de señales de comportamiento durante una
evaluación digital (dentro de la propia plataforma web, con APIs y eventos nativos del
navegador, sin extensión), procesamiento determinístico que genera indicadores
preliminares, un análisis poblacional (Isolation Forest) que se ejecuta una sola vez al
cerrar la evaluación, y un panel para que el docente revise esa evidencia. Los indicadores
**no** son una conclusión sobre el estudiante: priorizan la revisión humana.

Estado: **versión 1.0.0** (archivo [`VERSION`](VERSION)), Incremento 16. Ver
[`docs/bitacora.md`](docs/bitacora.md) para el registro de cada incremento (qué se hizo,
qué se probó y por qué) y [`ARCHITECTURE.md`](ARCHITECTURE.md) para cómo encajan las piezas
y su trazabilidad a los requerimientos.

## Estructura

```
mvp/
├── VERSION              Versión de la entrega (1.0.0)
├── backend/             API FastAPI + procesamiento + evaluación (ver backend/README.md)
│   ├── app/             API, procesamiento (reglas, cohorte al cierre), retención (RF17/RNF10)
│   ├── migrations/      Migraciones de Alembic (se aplican al arrancar)
│   ├── scripts/         evaluar.py, aporte_modelo.py, seed_*.py, purgar_vencidas.py, exportar/analizar sesiones
│   └── tests/           pytest
├── dashboard/           React + TypeScript: vista del estudiante (/rendir, /exam/:código) y
│                        panel docente (/exams, /sessions/..., /validaciones) (ver dashboard/README.md)
├── scripts/
│   ├── reproducir.sh          Punto de entrada único del paquete de reproducibilidad
│   ├── capturas_demo.py       Capturas de la demo de punta a punta (Playwright)
│   ├── prueba_interna.py      Prueba interna end-to-end con escenarios guionados (Playwright)
│   ├── prueba_red.py          Resiliencia de la captura ante cortes de red (Playwright)
│   ├── medir_rnf.py           Mediciones de RNF07, RNF09 y RNF11 sobre el sistema real
│   ├── evaluar_usabilidad.py  Evaluación experta y automatizada de usabilidad (Playwright + axe-core)
│   └── verificar_despliegue.py  Verificación de un despliegue (salud, login, flujo mínimo)
├── docker-compose.yml   Stack con PostgreSQL (ver «Con Docker»)
└── docs/
    ├── bitacora.md, despliegue.md, despliegue_vercel.md, simulaciones/protocolo.md
    └── evaluacion/      Resultados versionados (ver «Resultados vigentes»)
```

## Puesta en marcha rápida (sin Docker, para desarrollo local)

### 1. Backend

Con **Python 3.12** (los pines de `requirements.txt` no instalan en 3.13; ver backend/README.md):

```bash
cd mvp/backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --port 8010 &   # al arrancar aplica las migraciones y crea impronta.db
python -m scripts.seed_teacher docente@uade.edu.ar 1234
curl http://127.0.0.1:8010/health    # {"status":"ok","version":"1.0.0","commit":"desconocido"}
```

El backend tiene que arrancar ANTES del primer `seed_teacher` (crea la base con las
migraciones). Sin variables de entorno usa SQLite local y la configuración de desarrollo;
las variables de producción están en `docs/despliegue.md`.

### 2. Dashboard

```bash
cd mvp/dashboard
npm install
npm run dev
```

Abrir `http://localhost:5173`, ingresar con `docente@uade.edu.ar` / `1234` y crear una
evaluación (incluye la consigna que verá el estudiante). La lista muestra el código y un
botón «Copiar enlace».

### 3. Rendir (vista del estudiante)

1. Abrir `http://localhost:5173/rendir` e ingresar el código (o abrir directamente el
   enlace `http://localhost:5173/exam/{código}`), sin login.
2. Leer la información, las señales que se registran y las reglas; completar el código de
   participante, aceptar el consentimiento y **Comenzar**.
3. Responder la consigna. Si se corta la red se puede seguir escribiendo: los registros
   quedan en el navegador y se envían al reconectar. Recargar la página retoma la misma
   sesión con el borrador.
4. **Finalizar y entregar** (con confirmación). La entrega se confirma cuando el servidor
   procesó la sesión.
5. En el panel docente la sesión aparece en la evaluación; si alguna regla se disparó,
   queda marcada «Requiere revisión».

El modelo poblacional se ejecuta **al cerrar la evaluación** («Cerrar la evaluación y
analizar…»), sobre todas las sesiones finalizadas, y necesita al menos 20. Para una demo
con sesiones sintéticas (participantes `SINT-*`):

```bash
cd mvp/backend && python -m scripts.seed_demo --join-code {código} --normales 24 --atipicas 1
```

Eliminación de datos (RF17): una sesión desde su detalle, una evaluación completa desde su
pantalla («Eliminar esta evaluación…») y la cuenta del docente desde la lista de
evaluaciones («Eliminar mi cuenta…», pide la contraseña). Las sesiones con el plazo de
conservación vencido se purgan al arrancar el backend y con `python -m scripts.purgar_vencidas`.

### Datos de demostración para la presentación

`backend/scripts/seed_presentacion.py` deja el panel de un docente (`docente@uade.edu.ar` /
`1234`) con seis evaluaciones del cuatrimestre: dos parciales por comisión ya cerrados y
revisados, un TP a libro abierto, el Parcial 2 cerrado hace 3 días con la revisión a medias
(una validación pendiente) y un recuperatorio **abierto** con 19 entregas (al rendir una más
en vivo llega a 20 y el cierre ya ejecuta el modelo). Todo pasa por la API real; las sesiones
son sintéticas y los códigos `P-1xx` y las respuestas son inventados. Las fechas se calculan
desde el momento en que se corre, así que conviene correrlo el día de la presentación:

```bash
cd mvp/backend
python -m scripts.seed_presentacion --reiniciar   # ~2-3 min, sin levantar el backend
```

Para cargarla en la plataforma desplegada en la nube, ver «Cargar los datos de demostración en la
plataforma desplegada» en `docs/despliegue.md`.

## Correr los tests

```bash
cd mvp/backend && source .venv/bin/activate && pytest   # 142 pruebas del backend (1 de PostgreSQL omitida)
cd mvp/dashboard && npm test && npm run build           # 36 tests del dashboard + build
```

## Reproducibilidad

**Identificador inmutable.** La entrega final se identifica con el tag de git
**`v1.0`** del repositorio https://github.com/01juanf/ImprontIA-PFI.
Para reproducir, partir de ese tag (`git checkout v1.0`). La versión de la
aplicación (`VERSION`, 1.0.0) y el commit con el que se construyó se ven en:

- backend: `GET /health` y `GET /version` → `{"version": "1.0.0", "commit": "<hash>"}`
  (el commit sale de la variable `GIT_COMMIT`; sin ella, `"desconocido"`);
- dashboard: pie del panel y tarjeta de ingreso, «ImprontIA v1.0.0 · commit abc1234»
  (`VITE_GIT_COMMIT`, fijado al compilar).

Con Docker: `GIT_COMMIT=$(git rev-parse HEAD) docker compose up --build -d` pasa el commit
a las dos imágenes (build args `GIT_COMMIT` y `VITE_GIT_COMMIT`).

**Un solo comando** (desde `mvp/`, con el entorno del backend ya instalado en `backend/.venv`):

```bash
bash scripts/reproducir.sh --python backend/.venv/bin/python            # ~15 min
bash scripts/reproducir.sh --python backend/.venv/bin/python --rapido   # verificación rápida
bash scripts/reproducir.sh --ayuda                                      # todas las opciones
```

Se invoca con `bash` para que funcione igual desde un clon o desde el ZIP que descarga GitHub,
aunque el archivo no conserve el permiso de ejecución.

| Paso | Qué corre | Salida esperada |
|---|---|---|
| (a) | `pytest` del backend | 142 passed, 1 skipped (la omitida solo corre sobre PostgreSQL) |
| (b) | `npm test` y `npm run build` del dashboard | 36 pass, 0 fail; `dist/` |
| (c) | `backend/scripts/evaluar.py --protocolo cierre` (análisis de la cohorte al cierre, el protocolo del MVP) | `docs/evaluacion/resultados_sinteticos_inc16.{md,json}`, `sesiones_sinteticas_inc16.csv`, `roc_modelo_inc16.csv`, `barrido_dificultad_inc16.csv` |
| (d) | `backend/scripts/aporte_modelo.py` (30 semillas; `--rapido`: 5, en `docs/evaluacion/rapido/`) | `docs/evaluacion/aporte_modelo.{md,csv}` |
| (e) opcional | `--rnf`: `scripts/medir_rnf.py` (SQLite) · `--usabilidad --axe RUTA`: `scripts/evaluar_usabilidad.py` | `rnf_mediciones_sqlite.json` + `rnf_mediciones.md` · `usabilidad/metricas.json` + PNG |
| final | `git rev-parse HEAD` y hashes | commit impreso y `docs/evaluacion/MANIFIESTO.sha256` (`sha256sum -c docs/evaluacion/MANIFIESTO.sha256`) |

Los resultados sintéticos son deterministas (semillas fijas): con las mismas versiones de
Python, numpy y scikit-learn (`requirements.txt`) se obtienen los mismos números. Las
mediciones de tiempos (RNF) y los tiempos de la evaluación de usabilidad dependen de la
máquina. `--evaluar-previo` regenera además `resultados_sinteticos.md` con el protocolo
anterior (modelo entrenado con una población previa, Incremento 6), que ya no es el del MVP.

## Resultados vigentes (`docs/evaluacion/`)

Todos con datos **sintéticos** o recorridos automatizados: validan el procedimiento y el
comportamiento del sistema, no el desempeño con estudiantes reales.

| Archivo | Script | Qué es |
|---|---|---|
| `resultados_sinteticos_inc16.md` | `evaluar.py --protocolo cierre` | FAR/FRR/AUC/EER con el análisis al cierre |
| `resultados_sinteticos.md` | `evaluar.py` | Igual, con el protocolo anterior (Incremento 6, histórico) |
| `aporte_modelo.md` / `.csv` | `aporte_modelo.py` | Qué detecta el modelo que las reglas no, y a qué costo |
| `prueba_interna_inc16_resultados.md` | `prueba_interna.py --sufijo _inc16` | Prueba interna end-to-end vigente; `prueba_interna.md` tiene la interpretación (las corridas anteriores quedan como historial) |
| `prueba_red_resultados.md` | `prueba_red.py` | Resiliencia de la captura ante cortes de red |
| `rnf_mediciones.md` | `medir_rnf.py` | RNF07, RNF09 y RNF11 con SQLite y PostgreSQL |
| `usabilidad_resultados.md` | `evaluar_usabilidad.py` | Evaluación experta y automatizada de usabilidad (corrida 2, con «Antes / después»; la corrida 1 está en `usabilidad_resultados_v1.md`). No es una prueba con usuarios |
| `protocolo_prueba_manual.md` | — | Cómo repetir la prueba interna a mano |

## Capturas de la demo y pruebas end-to-end

Requieren Playwright para Python con Chromium (`pip install playwright` y
`playwright install chromium`) y `npm install` hecho en `dashboard/`. `capturas_demo.py`,
`prueba_interna.py` y `prueba_red.py` usan los puertos 8010 y 5173 (no tiene que haber otro
backend o dashboard corriendo); `evaluar_usabilidad.py` usa 8100 y 5180.

```bash
cd mvp
python scripts/capturas_demo.py --backend-python backend/.venv/bin/python                    # ~2 min
python scripts/prueba_interna.py --backend-python backend/.venv/bin/python --sufijo _inc16  # ~10 min
python scripts/prueba_red.py --backend-python backend/.venv/bin/python                       # ~3 min
mkdir -p /tmp/axe && (cd /tmp/axe && npm install axe-core@4.10.2)
python scripts/evaluar_usabilidad.py --backend-python backend/.venv/bin/python \
    --axe /tmp/axe/node_modules/axe-core/axe.min.js                                          # ~4 min
```

- `capturas_demo.py` levanta backend y dashboard con una base temporal, recorre el flujo
  crear evaluación → rendir y entregar → cerrar la evaluación → ver indicadores y panorama →
  revisar, y deja PNG numeradas en `docs/capturas/` (no versionadas; `--salida DIR` para
  otra carpeta).
- `prueba_interna.py` ejecuta escenarios guionados (sesión normal, pegado masivo, cambios
  de foco, transcripción a ritmo regular) en el navegador, verifica los indicadores (API y
  dashboard), que no se guarde texto en los eventos y que se guarde la respuesta.
- `prueba_red.py` simula un corte de red prolongado, un buffer lleno y una reconexión, y
  verifica el backoff, que no se pierdan pulsaciones sin registro y el aviso de captura
  incompleta para el docente.

## Con Docker (stack completo, PostgreSQL real)

```bash
cd mvp
cp .env.example .env                       # completar JWT_SECRET (obligatorio)
GIT_COMMIT=$(git rev-parse HEAD) docker compose up --build -d
docker compose exec backend python -m scripts.seed_teacher docente@uade.edu.ar 1234
```

Dashboard en `http://localhost:5173`, API en `http://localhost:8010` (`/health`). Detalle,
variables y despliegue en Render: `docs/despliegue.md`. Despliegue en Vercel con base en Neon
(URL pública gratuita): `docs/despliegue_vercel.md`.

**No validado de punta a punta.** `docker compose config` valida el archivo (incluidos los
build args del commit), pero el stack completo no se construyó ni se levantó en el entorno de
desarrollo de esta entrega: el 22/10 `docker compose build` falló al descargar la imagen base
`python:3.12-slim` (el registro de Docker Hub no era accesible desde ese entorno). Las
mediciones con PostgreSQL de `rnf_mediciones.md` se hicieron con un PostgreSQL 16 instalado en la
máquina, sin Docker (el compose usa la imagen `postgres:15`).
