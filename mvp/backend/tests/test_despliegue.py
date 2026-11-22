"""
Fase 2, P01: configuración para el despliegue (app/config.py).

Sin variables de entorno el comportamiento es el de desarrollo de siempre; con
IMPRONTIA_ENV=production el backend exige un JWT_SECRET propio.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.config import (
    DEFAULT_SQLITE_URL,
    DEV_JWT_SECRET,
    DEFAULT_POOL_MAX,
    DEFAULT_POOL_SIZE,
    cors_origins,
    db_pool_limits,
    jwt_secret,
    normalize_database_url,
    seed_teachers,
)

BACKEND = Path(__file__).resolve().parent.parent
GOOD_SECRET = "x" * 48


def test_database_url_accepts_the_managed_services_format():
    assert normalize_database_url(None) == DEFAULT_SQLITE_URL
    assert normalize_database_url("") == DEFAULT_SQLITE_URL
    assert normalize_database_url("postgres://u:p@h:5432/db") == "postgresql+psycopg2://u:p@h:5432/db"
    assert normalize_database_url("postgresql://u:p@h/db") == "postgresql+psycopg2://u:p@h/db"
    # Las URL que ya traen driver, y SQLite, no se tocan.
    assert normalize_database_url("postgresql+psycopg2://u:p@h/db") == "postgresql+psycopg2://u:p@h/db"
    assert normalize_database_url("sqlite:///./x.db") == "sqlite:///./x.db"


@pytest.mark.parametrize("url", [
    "postgres://u:p@ep-x-pooler.sa-east-1.aws.neon.tech/neondb?sslmode=require",
    "postgresql://u:p@ep-x-pooler.sa-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require",
    "postgresql://postgres.ref:p@aws-0-sa-east-1.pooler.supabase.com:5432/postgres?sslmode=require",
])
def test_database_url_keeps_ssl_parameters_of_managed_providers(url):
    """Neon/Supabase entregan la URL con ?sslmode=require (y a veces channel_binding): no se pierden."""
    from sqlalchemy.engine import make_url

    out = make_url(normalize_database_url(url))
    assert out.drivername == "postgresql+psycopg2"
    assert out.query["sslmode"] == "require"
    if "channel_binding" in url:
        assert out.query["channel_binding"] == "require"
    assert out.password == "p"


def test_postgres_engine_survives_connections_cut_by_the_provider():
    """pool_pre_ping + pool_recycle: una conexión cortada por inactividad no hace fallar un request."""
    from app.database import CONNECT_TIMEOUT_S, engine_kwargs

    kw = engine_kwargs("postgresql+psycopg2://u:p@h/db?sslmode=require")
    assert kw["pool_pre_ping"] is True
    assert 0 < kw["pool_recycle"] <= 300
    assert kw["connect_args"] == {"connect_timeout": CONNECT_TIMEOUT_S}
    assert kw["pool_size"] == DEFAULT_POOL_SIZE
    assert kw["pool_size"] + kw["max_overflow"] == DEFAULT_POOL_MAX
    # Si la URL ya trae connect_timeout, se respeta el de la URL.
    assert "connect_args" not in engine_kwargs("postgresql+psycopg2://u:p@h/db?connect_timeout=5")
    # SQLite sigue como antes (sin pre_ping; sin pool para :memory:).
    assert "pool_pre_ping" not in engine_kwargs("sqlite:///./x.db")
    assert "pool_size" not in engine_kwargs("sqlite:///:memory:")


def test_postgres_engine_connects_with_the_provider_url_format():
    """Con TEST_DATABASE_URL (PostgreSQL) se arma un engine desde `postgres://…?sslmode=…` y conecta."""
    url = os.environ.get("TEST_DATABASE_URL", "")
    if not url.startswith(("postgres://", "postgresql://")):
        pytest.skip("solo con TEST_DATABASE_URL apuntando a PostgreSQL")
    from sqlalchemy import create_engine, text

    from app.database import engine_kwargs

    raw = "postgres://" + url.split("://", 1)[1]
    if "sslmode=" not in raw:  # los proveedores la mandan con sslmode=require; local alcanza prefer
        raw += ("&" if "?" in raw else "?") + "sslmode=prefer"
    norm = normalize_database_url(raw)
    eng = create_engine(norm, **engine_kwargs(norm))
    try:
        with eng.connect() as conn:
            assert conn.execute(text("SELECT 1")).scalar() == 1
    finally:
        eng.dispose()


def test_db_pool_limits_defaults_and_validation():
    assert db_pool_limits({}) == (DEFAULT_POOL_SIZE, DEFAULT_POOL_MAX)
    assert db_pool_limits({"DB_POOL_SIZE": "3", "DB_POOL_MAX": "20"}) == (3, 20)
    for bad in ({"DB_POOL_MAX": "8"}, {"DB_POOL_SIZE": "0"}, {"DB_POOL_SIZE": "50"}, {"DB_POOL_MAX": "muchas"}):
        with pytest.raises(RuntimeError):
            db_pool_limits(bad)


def test_jwt_secret_keeps_the_dev_default_outside_production():
    assert jwt_secret({}) == DEV_JWT_SECRET
    assert jwt_secret({"JWT_SECRET": "otro"}) == "otro"


@pytest.mark.parametrize("secret", [None, "", DEV_JWT_SECRET, "change-me-in-production", "corto"])
def test_jwt_secret_is_mandatory_in_production(secret):
    env = {"IMPRONTIA_ENV": "production"}
    if secret is not None:
        env["JWT_SECRET"] = secret
    with pytest.raises(RuntimeError):
        jwt_secret(env)


def test_jwt_secret_in_production_with_a_real_secret():
    assert jwt_secret({"IMPRONTIA_ENV": "Production", "JWT_SECRET": GOOD_SECRET}) == GOOD_SECRET


def test_cors_origins_default_and_list():
    assert cors_origins({}) == ["http://localhost:5173"]
    assert cors_origins({"CORS_ORIGINS": " https://a.onrender.com/ , http://localhost:5173 ,"}) == [
        "https://a.onrender.com", "http://localhost:5173",
    ]


def test_seed_teachers_parsing():
    assert seed_teachers({}) == []
    assert seed_teachers({"SEED_TEACHERS": "a@x.com:uno, b@y.com:dos:con:dos-puntos"}) == [
        ("a@x.com", "uno"), ("b@y.com", "dos:con:dos-puntos"),
    ]
    with pytest.raises(RuntimeError):
        seed_teachers({"SEED_TEACHERS": "sin-clave@x.com"})


def test_seed_teachers_creates_missing_users_and_never_resets_a_password(client, monkeypatch):
    from app.main import seed_teachers_from_env

    monkeypatch.setenv("SEED_TEACHERS", "seed-1@uade.edu.ar:clave-1,seed-2@uade.edu.ar:clave-2")
    assert sorted(seed_teachers_from_env()) == ["seed-1@uade.edu.ar", "seed-2@uade.edu.ar"]
    assert seed_teachers_from_env() == []  # idempotente

    monkeypatch.setenv("SEED_TEACHERS", "seed-1@uade.edu.ar:otra-clave")
    assert seed_teachers_from_env() == []
    ok = client.post("/auth/login", json={"email": "seed-1@uade.edu.ar", "password": "clave-1"})
    assert ok.status_code == 200
    assert client.post("/auth/login", json={"email": "seed-1@uade.edu.ar", "password": "otra-clave"}).status_code == 401


def _import_app(tmp_path, **env_extra) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k not in ("JWT_SECRET", "IMPRONTIA_ENV", "SEED_TEACHERS")}
    env.update({"DATABASE_URL": f"sqlite:///{tmp_path / 'prod.db'}", "IMPRONTIA_ENV": "production", **env_extra})
    return subprocess.run(
        [sys.executable, "-c", "import app.main; print('ARRANCA')"],
        cwd=BACKEND, env=env, capture_output=True, text=True, timeout=60,
    )


def test_backend_refuses_to_start_in_production_without_jwt_secret(tmp_path):
    r = _import_app(tmp_path)
    assert r.returncode != 0
    assert "JWT_SECRET es obligatorio" in r.stderr

    r = _import_app(tmp_path, JWT_SECRET=GOOD_SECRET)
    assert r.returncode == 0, r.stderr
    assert "ARRANCA" in r.stdout


# ---- Despliegue en Vercel (nov. 2026) ----

def test_migrate_on_startup_flag():
    from app.config import migrate_on_startup

    assert migrate_on_startup({}) is True
    assert migrate_on_startup({"MIGRATE_ON_STARTUP": "1"}) is True
    assert migrate_on_startup({"MIGRATE_ON_STARTUP": "0"}) is False
    assert migrate_on_startup({"MIGRATE_ON_STARTUP": "false"}) is False
    with pytest.raises(RuntimeError):
        migrate_on_startup({"MIGRATE_ON_STARTUP": "quizas"})


def test_vercel_build_migrates_seeds_and_then_the_app_starts(tmp_path):
    env = {k: v for k, v in os.environ.items() if k not in ("JWT_SECRET", "IMPRONTIA_ENV", "SEED_TEACHERS")}
    env.update({"DATABASE_URL": f"sqlite:///{tmp_path / 'prod.db'}", "IMPRONTIA_ENV": "production",
                "JWT_SECRET": GOOD_SECRET, "SEED_TEACHERS": "a@uade.edu.ar:clave-larga-123"})
    build = subprocess.run([sys.executable, "-m", "scripts.vercel_build"], cwd=BACKEND, env=env,
                           capture_output=True, text=True, timeout=120)
    assert build.returncode == 0, build.stderr
    assert "a@uade.edu.ar" in build.stdout

    # La función arranca sin migrar ni sembrar (MIGRATE_ON_STARTUP=0): no crea al docente nuevo.
    r = _import_app(tmp_path, JWT_SECRET=GOOD_SECRET, MIGRATE_ON_STARTUP="0",
                    SEED_TEACHERS="b@uade.edu.ar:clave-larga-456")
    assert r.returncode == 0, r.stderr
    import sqlite3

    mails = {m for (m,) in sqlite3.connect(tmp_path / "prod.db").execute("select email from users")}
    assert mails == {"a@uade.edu.ar"}

    # Volver a correr el build (otro despliegue) es idempotente y suma solo lo que falta.
    env["SEED_TEACHERS"] = "a@uade.edu.ar:clave-larga-123,b@uade.edu.ar:clave-larga-456"
    again = subprocess.run([sys.executable, "-m", "scripts.vercel_build"], cwd=BACKEND, env=env,
                           capture_output=True, text=True, timeout=120)
    assert again.returncode == 0, again.stderr
    assert "b@uade.edu.ar" in again.stdout and "a@uade.edu.ar" not in again.stdout


def test_vercel_build_refuses_without_database_url():
    env = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}
    r = subprocess.run([sys.executable, "-m", "scripts.vercel_build"], cwd=BACKEND, env=env,
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 1
    assert "falta DATABASE_URL" in r.stderr


def test_version_takes_the_vercel_commit():
    from app.version import git_commit

    assert git_commit({"VERCEL_GIT_COMMIT_SHA": "abc123"}) == "abc123"
    assert git_commit({"GIT_COMMIT": "def456", "VERCEL_GIT_COMMIT_SHA": "abc123"}) == "def456"
