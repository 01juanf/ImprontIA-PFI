# ImprontIA — Backend

FastAPI + SQLAlchemy. Ver `../docs/bitacora.md` para el razonamiento
detrás de cada decisión (Incremento 1: esqueleto; Incremento 5: rediseño
de esquema + Isolation Forest; Incremento 6: evaluación reproducible;
Incremento 8: estado de revisión / validación adicional; Incremento 9:
prueba interna end-to-end y pulsaciones sin identificar la tecla;
Incremento 10: nivel del indicador de IA por percentiles e integridad de la
captura; Incremento 11: cierre de los hallazgos de la revisión del 14/10)
y `../ARCHITECTURE.md` para la trazabilidad a los requerimientos de la tesis.

## Setup

Usar **Python 3.11 o 3.12** (con 3.13 los pines actuales de
`psycopg2-binary` y `numpy` no instalan; ver bitácora, "Línea de base").

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m scripts.seed_teacher <email> <password>   # crea/actualiza un docente
uvicorn app.main:app --port 8010
```

Documentación interactiva de la API (Swagger): `http://127.0.0.1:8010/docs`.

## Configuración

| Variable | Default | Descripción |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./impronta.db` | Cadena de conexión SQLAlchemy. Con Docker Compose se setea a PostgreSQL. |
| `JWT_SECRET` | `dev-secret-change-me` | Secreto de firma de tokens. **Cambiar en cualquier entorno real.** |

## Tests

```bash
pytest              # 56 tests: features (8), indicadores (4), anomaly (3), evaluación (15),
                    # API (9), política/trazabilidad (7), estado de revisión (4), incremento 10 (6)
pytest -v           # con detalle
```

Los avisos de deprecación que quedan al correr `pytest` (≈ 50) vienen de
dependencias de terceros (`python-jose`, `passlib`, `starlette`), no del
código del MVP; ver bitácora, Incremento 11.

Las pruebas de sistema de punta a punta (navegador + backend + dashboard)
son `../scripts/prueba_interna.py` y `../scripts/prueba_red.py`; ver
`../README.md`.

## Scripts

```bash
python -m scripts.seed_teacher <email> <password>       # alta/reset de docente
python -m scripts.evaluar                               # evaluación con datos sintéticos (~5 min)
python -m scripts.evaluar --repeticiones 5 --sin-barrido  # versión rápida
python -m scripts.seed_demo --join-code ABC123          # carga sesiones sintéticas vía API (backend corriendo)
```

`scripts/evaluar.py` escribe en `../docs/evaluacion/` (reporte
`resultados_sinteticos.md` + CSV para gráficos). Son **datos sintéticos**:
validan el procedimiento de medición (FAR, FRR, AUC-ROC, AP, EER), no el
desempeño real del sistema.

## Estructura

```
app/
├── main.py              FastAPI app, CORS, creación de tablas
├── database.py          Engine/Session de SQLAlchemy
├── models.py             Exam, PolicyCapture, Session, Event, Metric,
│                          Indicator, IndicatorMetric, Review, ReviewIndicator, User
├── schemas.py             Pydantic (request/response); fechas siempre en UTC explícito
├── auth.py                JWT del docente (el token de sesión del estudiante se valida en routers/sessions.py)
├── routers/
│   ├── auth.py            POST /auth/login
│   ├── exams.py           CRUD de evaluaciones, versionado de política, info pública (join_code)
│   └── sessions.py        Ciclo de vida de sesión + procesamiento (_run_processing: único punto que
│                          lee y escribe la base al finalizar) + reviews + estado de revisión
├── processing/            Funciones puras, sin acceso a la base
│   ├── features.py         Extracción determinística de métricas, incluida la integridad de la
│   │                       captura (eventos descartados, fallas de sincronización)
│   ├── indicators.py        Métricas -> indicadores preliminares (umbrales explícitos, nivel del
│   │                        indicador de IA por percentil, aviso informativo de captura incompleta)
│   ├── anomaly.py            Isolation Forest sobre línea base poblacional (métricas continuas)
│   │                         + percentil de la sesión dentro de esa línea base
│   └── pipeline.py           Reglas + modelo para una sesión (lo usan la API y la evaluación)
└── evaluation/
    ├── synthetic.py          Generador de sesiones sintéticas (normal + 4 perfiles anómalos)
    ├── metrics.py            FAR/FRR/EER/AUC-ROC/AP (convención: positivo = anómala)
    └── experiment.py         Protocolo de repeticiones con semillas fijas
scripts/
├── seed_teacher.py        Alta de docentes
├── evaluar.py             Evaluación reproducible -> docs/evaluacion/
└── seed_demo.py           Población sintética vía API (para la demo, las capturas y la prueba interna)
```
