"""
Migraciones de esquema con Alembic (Fase 2, P02).

Hasta el Incremento 13 el backend creaba las tablas con `Base.metadata.create_all`.
Desde P02 el esquema lo crean y lo evolucionan las migraciones de `migrations/`,
y el backend las aplica solo al arrancar (`upgrade head`), así una base con datos
reales se actualiza sin borrarla:

- Base vacía (instalación nueva, tests): se aplican todas las migraciones.
- Base creada antes de P02 (tiene las tablas pero no `alembic_version`): se marca en
  la revisión inicial, que reproduce exactamente ese esquema, y se aplican las
  siguientes. Los datos no se tocan.
- Base ya migrada: se aplican solo las revisiones pendientes (si no hay, no hace nada).
"""
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import inspect
from sqlalchemy.engine import Engine

BACKEND_DIR = Path(__file__).resolve().parent.parent
BASELINE_REVISION = "0001_esquema_inicial"
HEAD_REVISION = "0005_ejercicios_y_pdf"


def alembic_config() -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    return cfg


def current_revision(engine: Engine) -> str | None:
    with engine.connect() as conn:
        return MigrationContext.configure(conn).get_current_revision()


def _matches_models(conn) -> bool:
    """¿El esquema existente es exactamente el de models.py (sin contar alembic_version)?"""
    from alembic.autogenerate import compare_metadata

    from . import models  # noqa: F401  (registra las tablas)
    from .database import Base

    diffs = compare_metadata(MigrationContext.configure(conn, opts={"compare_type": True}), Base.metadata)
    return not diffs


def upgrade_db(engine: Engine, revision: str = "head") -> str:
    """Lleva la base a `revision`. Devuelve qué hizo: "upgrade", "stamp+upgrade" o "stamp"."""
    action = "upgrade"
    with engine.begin() as conn:
        cfg = alembic_config()
        cfg.attributes["connection"] = conn
        tables = set(inspect(conn).get_table_names())
        if "users" in tables and "alembic_version" not in tables:
            if revision == "head" and _matches_models(conn):
                # Base creada con create_all del esquema ACTUAL (p. ej. por el viejo
                # scripts/seed_teacher.py): ya está en head, solo falta marcarla. Antes se la
                # marcaba en la revisión inicial y la 0002 fallaba por columnas duplicadas.
                command.stamp(cfg, "head")
                return "stamp"
            # Base creada con create_all antes de P02: su esquema es el de la revisión inicial.
            command.stamp(cfg, BASELINE_REVISION)
            action = "stamp+upgrade"
        command.upgrade(cfg, revision)
    return action


def downgrade_db(engine: Engine, revision: str) -> None:
    with engine.begin() as conn:
        cfg = alembic_config()
        cfg.attributes["connection"] = conn
        command.downgrade(cfg, revision)
