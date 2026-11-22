"""
Configuración por variables de entorno para el despliegue (Fase 2, P01).

Sin ninguna variable seteada el comportamiento es exactamente el de desarrollo
(SQLite local, CORS para el Vite en localhost:5173, secreto JWT de desarrollo),
así que los tests y la evaluación no cambian. En producción
(`IMPRONTIA_ENV=production`) el backend se niega a arrancar sin un `JWT_SECRET`
propio: con el secreto de desarrollo, cualquiera podría firmar tokens de docente.

Variables:
- IMPRONTIA_ENV       "production" activa las validaciones de abajo (default: "development").
- DATABASE_URL        URL de la base. Acepta el formato que entregan Render/Railway/Neon
                      (`postgres://` o `postgresql://`) y lo normaliza al driver psycopg2.
- JWT_SECRET          secreto para firmar los tokens del docente. Obligatorio en producción
                      (mínimo 32 caracteres; generarlo con `python -c "import secrets; print(secrets.token_urlsafe(48))"`).
- CORS_ORIGINS        orígenes del dashboard separados por coma (default: http://localhost:5173).
- SEED_TEACHERS       docentes a crear al arrancar si no existen: "mail1:clave1,mail2:clave2".
                      Sirve en servicios gratuitos sin consola; nunca cambia la clave de un docente existente.
- DB_POOL_SIZE        (opcional) conexiones a PostgreSQL que el backend mantiene abiertas en reposo (default 5).
- DB_POOL_MAX         (opcional) máximo de conexiones simultáneas a PostgreSQL (default 40, mínimo 12).
- MIGRATE_ON_STARTUP  (opcional) "0" para NO aplicar las migraciones ni crear los SEED_TEACHERS al
                      arrancar. En Vercel cada arranque en frío de la función repetiría ese trabajo, así que
                      se hace una sola vez en el build (scripts/vercel_build.py). Default: "1" (se aplican).
                      Bajarlo solo si el proveedor admite pocas conexiones (ver docs/despliegue.md).
"""
import os
from typing import Mapping, Optional

DEV_JWT_SECRET = "dev-secret-change-me"
DEFAULT_SQLITE_URL = "sqlite:///./impronta.db"
DEFAULT_CORS_ORIGINS = ["http://localhost:5173"]
MIN_SECRET_LENGTH = 32

# Pool de conexiones a PostgreSQL (despliegue en la nube, 30/10/2026). El máximo (40) es el que
# fijó la revisión del Incremento 16 para que cada hilo del threadpool tenga su conexión (RNF09);
# de esas, solo DEFAULT_POOL_SIZE quedan abiertas en reposo: las bases gestionadas (Render, Neon,
# Supabase) limitan las conexiones y cortan las inactivas, y no tiene sentido retener 20 ociosas.
DEFAULT_POOL_SIZE = 5
DEFAULT_POOL_MAX = 40
MIN_POOL_MAX = 12  # main.MAX_REQUESTS_IN_FLIGHT = min(hilos, máximo) - 8: con menos de 12 queda < 4.


def _env(env: Optional[Mapping[str, str]]) -> Mapping[str, str]:
    return os.environ if env is None else env


def is_production(env: Optional[Mapping[str, str]] = None) -> bool:
    return _env(env).get("IMPRONTIA_ENV", "development").strip().lower() == "production"


def normalize_database_url(url: Optional[str]) -> str:
    """`postgres://…` y `postgresql://…` (formato de los servicios gestionados) -> `postgresql+psycopg2://…`."""
    if not url:
        return DEFAULT_SQLITE_URL
    url = url.strip()
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg2://" + url[len(prefix):]
    return url


def database_url(env: Optional[Mapping[str, str]] = None) -> str:
    return normalize_database_url(_env(env).get("DATABASE_URL"))


def jwt_secret(env: Optional[Mapping[str, str]] = None) -> str:
    e = _env(env)
    secret = e.get("JWT_SECRET", "").strip()
    if is_production(e):
        if not secret or secret == DEV_JWT_SECRET or secret.startswith("change-me"):
            raise RuntimeError(
                "JWT_SECRET es obligatorio en producción (IMPRONTIA_ENV=production). "
                "Generalo con: python -c \"import secrets; print(secrets.token_urlsafe(48))\""
            )
        if len(secret) < MIN_SECRET_LENGTH:
            raise RuntimeError(f"JWT_SECRET demasiado corto: se piden al menos {MIN_SECRET_LENGTH} caracteres.")
        return secret
    return secret or DEV_JWT_SECRET


def cors_origins(env: Optional[Mapping[str, str]] = None) -> list[str]:
    raw = _env(env).get("CORS_ORIGINS", "")
    origins = [o.strip().rstrip("/") for o in raw.split(",") if o.strip()]
    return origins or list(DEFAULT_CORS_ORIGINS)


def seed_teachers(env: Optional[Mapping[str, str]] = None) -> list[tuple[str, str]]:
    """'a@x.com:clave1,b@y.com:clave2' -> [(email, clave), ...]. La clave puede contener ':'."""
    out = []
    for item in _env(env).get("SEED_TEACHERS", "").split(","):
        item = item.strip()
        if not item:
            continue
        email, sep, password = item.partition(":")
        if not sep or not email.strip() or not password:
            raise RuntimeError("SEED_TEACHERS mal formado: se espera 'mail:clave' separados por coma.")
        out.append((email.strip(), password))
    return out


def _int_env(e: Mapping[str, str], key: str, default: int) -> int:
    raw = e.get(key, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        raise RuntimeError(f"{key} debe ser un número entero (vino {raw!r}).") from None


def db_pool_limits(env: Optional[Mapping[str, str]] = None) -> tuple[int, int]:
    """(conexiones en reposo, máximo de conexiones) del pool de PostgreSQL, con DB_POOL_SIZE / DB_POOL_MAX."""
    e = _env(env)
    maximo = _int_env(e, "DB_POOL_MAX", DEFAULT_POOL_MAX)
    if maximo < MIN_POOL_MAX:
        raise RuntimeError(f"DB_POOL_MAX debe ser al menos {MIN_POOL_MAX} (vino {maximo}).")
    reposo = _int_env(e, "DB_POOL_SIZE", min(DEFAULT_POOL_SIZE, maximo))
    if not 1 <= reposo <= maximo:
        raise RuntimeError(f"DB_POOL_SIZE debe estar entre 1 y DB_POOL_MAX ({maximo}); vino {reposo}.")
    return reposo, maximo


def migrate_on_startup(env: Optional[Mapping[str, str]] = None) -> bool:
    """¿Aplicar migraciones y SEED_TEACHERS al arrancar? (MIGRATE_ON_STARTUP, default sí)."""
    raw = _env(env).get("MIGRATE_ON_STARTUP", "1").strip().lower()
    if raw in ("1", "true", "yes", "si", "sí", ""):
        return True
    if raw in ("0", "false", "no"):
        return False
    raise RuntimeError(f"MIGRATE_ON_STARTUP debe ser 1 o 0 (vino {raw!r}).")
