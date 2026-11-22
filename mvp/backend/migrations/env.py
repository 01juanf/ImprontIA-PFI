"""
Entorno de Alembic (Fase 2, P02).

- La URL sale de DATABASE_URL (app/config.py), con la misma normalización que usa el
  backend (`postgres://` -> `postgresql+psycopg2://`); sin variable, SQLite local.
- Si quien llama ya pasa una conexión (app/db_migrations.py, los tests), se usa esa.
- `render_as_batch=True`: SQLite no soporta ALTER COLUMN/DROP COLUMN, así que las
  migraciones se escriben con `batch_alter_table` y corren igual en los dos motores.
- No se configura logging desde acá a propósito: el backend importa este módulo al
  arrancar y no debe pisar la configuración de logging de uvicorn.
"""
from alembic import context
from sqlalchemy import create_engine, pool

from app import models  # noqa: F401  (registra las tablas en Base.metadata, para --autogenerate)
from app.config import database_url
from app.database import Base

config = context.config
target_metadata = Base.metadata


def _configure(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url") or database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        _configure(connection)
        return
    url = config.get_main_option("sqlalchemy.url") or database_url()
    engine = create_engine(url, poolclass=pool.NullPool)
    with engine.connect() as conn:
        _configure(conn)
        conn.commit()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
