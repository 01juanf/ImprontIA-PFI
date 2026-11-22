import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import models
from .auth import hash_password
from .config import cors_origins, migrate_on_startup, seed_teachers
from .database import POOL_KWARGS, THREADPOOL_SIZE, SessionLocal, engine
from .db_migrations import upgrade_db
from .routers import auth, exams, sessions
from .version import app_version, version_info

# Fase 2 (P02): el esquema lo crean y lo evolucionan las migraciones de Alembic
# (migrations/), no `create_all`. Al arrancar se aplica `upgrade head`; una base creada
# antes de P02 se marca en la revisión inicial y se actualiza sin perder datos.
# Ver app/db_migrations.py y mvp/docs/bitacora.md (Incremento 14).
# Despliegue en Vercel (nov. 2026): con MIGRATE_ON_STARTUP=0 las migraciones y los SEED_TEACHERS
# no se aplican al arrancar, porque cada arranque en frío de la función lo repetiría; los
# aplica una sola vez el build (scripts/vercel_build.py, run_migrations_and_seed).


def seed_teachers_from_env() -> list[str]:
    """
    Fase 2 (P01): crea los docentes de SEED_TEACHERS si todavía no existen. Pensado para
    servicios gratuitos sin consola (Render free), donde no se puede correr
    scripts.seed_teacher. Nunca modifica la clave de un docente que ya existe.
    """
    created = []
    pairs = seed_teachers()
    if not pairs:
        return created
    db = SessionLocal()
    try:
        for email, password in pairs:
            if not db.query(models.User).filter(models.User.email == email).first():
                db.add(models.User(email=email, password_hash=hash_password(password)))
                created.append(email)
        db.commit()
    finally:
        db.close()
    return created


def run_migrations_and_seed() -> list[str]:
    """Aplica las migraciones pendientes y crea los SEED_TEACHERS que falten."""
    upgrade_db(engine)
    return seed_teachers_from_env()


if migrate_on_startup():
    run_migrations_and_seed()


def purge_on_startup() -> int:
    """RNF10 (Incremento 16): al arrancar se eliminan las sesiones con el plazo vencido."""
    from .retention import purge_expired

    db = SessionLocal()
    try:
        return purge_expired(db)
    finally:
        db.close()


purge_on_startup()

class ConcurrencyLimit:
    """
    Revisión del Incremento 16 (mediciones de RNF09): limita los requests HTTP en curso.

    FastAPI ejecuta cada dependencia síncrona (`get_session_by_token`, `get_current_teacher`)
    en un salto propio al pool de hilos, ANTES del endpoint. Con 200 entregas simultáneas, los
    requests que ya habían tomado una conexión de la base esperaban un hilo libre para el
    endpoint, mientras los 40 hilos estaban ocupados por dependencias de otros requests que
    esperaban una conexión: un bloqueo mutuo que solo se cortaba al vencer el timeout del pool
    (500 a los 30 s). Con a lo sumo `limit` requests adentro (menos que hilos y que
    conexiones), cada uno siempre consigue ambos; el resto espera su turno en el event loop.
    """

    def __init__(self, app, limit: int):
        self.app = app
        self.limit = limit
        self._sem = asyncio.Semaphore(limit)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        async with self._sem:
            await self.app(scope, receive, send)


MAX_REQUESTS_IN_FLIGHT = min(THREADPOOL_SIZE, POOL_KWARGS["pool_size"] + POOL_KWARGS["max_overflow"]) - 8

app = FastAPI(title="ImprontIA API", version=app_version())

app.add_middleware(
    CORSMiddleware,
    # Default: el dashboard Vite en dev (http://localhost:5173). En el despliegue se fija
    # con CORS_ORIGINS (URL pública del dashboard), ver docs/despliegue.md.
    allow_origins=cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(ConcurrencyLimit, limit=MAX_REQUESTS_IN_FLIGHT)  # la más externa

app.include_router(auth.router)
app.include_router(exams.router)
app.include_router(sessions.router)


@app.get("/health")
def health():
    # Paquete de reproducibilidad: versión y commit con los que se construyó (app/version.py).
    return {"status": "ok", **version_info()}


@app.get("/version")
def version():
    return version_info()
