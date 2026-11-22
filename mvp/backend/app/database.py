"""
Configuración de acceso a datos.

Decisión de alcance (ver mvp/docs/bitacora.md, Incremento 1):
La tesis (cap. 15 "Tecnologías") define PostgreSQL como motor único.
Para desarrollo local sin Docker, DATABASE_URL cae por defecto a SQLite.
Cambiar a Postgres es solo cuestión de setear la variable de entorno:

    DATABASE_URL=postgresql+psycopg2://user:pass@localhost:5432/impronta

Los modelos usan JSONB con variante JSON para SQLite (ver models.py),
por lo que el mismo código corre sobre ambos motores sin cambios.
"""
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import database_url, db_pool_limits

# Fase 2 (P01): acepta también `postgres://…` / `postgresql://…`, el formato que dan los
# servicios gestionados (Render, Railway, Neon, Supabase), y lo normaliza al driver psycopg2.
# Los parámetros de la URL (`?sslmode=require`, `&channel_binding=require`, …) pasan tal cual a libpq.
DATABASE_URL = database_url()

# Revisión del Incremento 16 (mediciones de RNF09, docs/evaluacion/rnf_mediciones.md): los
# endpoints son síncronos y FastAPI los corre en un pool de 40 hilos (anyio), pero el pool de
# conexiones por defecto de SQLAlchemy admite 15 (5 + 10). Con 200 estudiantes entregando a la
# vez, los requests que esperaban conexión más de 30 s fallaban con 500 (QueuePool limit). El
# pool se dimensiona para que cada hilo tenga su conexión: el request espera su turno en vez
# de fallar. 40 conexiones entran en el límite de los planes gestionados habituales.
THREADPOOL_SIZE = 40

# Despliegue en la nube (30/10/2026): de esas 40, solo DB_POOL_SIZE (default 5) quedan abiertas en
# reposo; el resto se abre en los picos y se cierra al devolverse. Ver app/config.py.
_POOL_SIZE, _POOL_MAX = db_pool_limits()
POOL_KWARGS = {"pool_size": _POOL_SIZE, "max_overflow": _POOL_MAX - _POOL_SIZE, "pool_timeout": 120}

# Conexiones a PostgreSQL gestionado: los proveedores cortan las conexiones inactivas (y Neon
# suspende la base tras unos minutos sin uso), así que:
# - pool_pre_ping: antes de usar una conexión del pool se verifica con un SELECT 1 y, si el
#   proveedor la cortó, se descarta y se abre otra (no falla el primer request tras un rato).
# - pool_recycle: ninguna conexión se reutiliza con más de 5 min de antigüedad.
# - connect_timeout: si la base no responde, el request falla en 15 s en vez de colgarse.
POSTGRES_ENGINE_KWARGS = {"pool_pre_ping": True, "pool_recycle": 300}
CONNECT_TIMEOUT_S = 15


def engine_kwargs(url: str) -> dict:
    """Argumentos de create_engine según el motor (separado para poder testearlo sin conectarse)."""
    if url.startswith("sqlite"):
        kwargs = {"connect_args": {"check_same_thread": False}}
        if ":memory:" not in url:
            kwargs.update(POOL_KWARGS)
        return kwargs
    kwargs = {**POOL_KWARGS, **POSTGRES_ENGINE_KWARGS}
    if "connect_timeout" not in make_url(url).query:  # si la URL ya lo trae, manda la URL
        kwargs["connect_args"] = {"connect_timeout": CONNECT_TIMEOUT_S}
    return kwargs


engine = create_engine(DATABASE_URL, **engine_kwargs(DATABASE_URL))

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
