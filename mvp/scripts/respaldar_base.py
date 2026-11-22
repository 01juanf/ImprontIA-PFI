"""
Respaldo de la base de ImprontIA con pg_dump (despliegue en la nube, 30/10/2026).

Hace una copia completa de la base PostgreSQL (Render, Neon, Supabase o la de Docker Compose)
en un archivo con fecha: respaldos/improntia_AAAA-MM-DD_HHMM.dump (formato "custom" de
pg_dump: comprimido, y se restaura con scripts/restaurar_base.py).

Uso (desde mvp/; la URL va en una variable de entorno, NUNCA como argumento):

    export DATABASE_URL='postgresql://usuario:clave@host/base?sslmode=require'
    python scripts/respaldar_base.py                 # -> respaldos/improntia_2026-10-30_1530.dump
    python scripts/respaldar_base.py --dir ~/Respaldos

Requisitos: pg_dump instalado, de la MISMA versión mayor que el servidor o más nueva
(con pg_dump 16 no se puede respaldar una base PostgreSQL 17). `--version` lo muestra.

Seguridad:
- No imprime la clave: la URL se muestra como usuario:***@host. La clave se le pasa a pg_dump
  por la variable PGPASSWORD (no queda en la línea de comandos ni en `ps`).
- El archivo contiene TODOS los datos (sesiones de estudiantes, docentes con sus hashes de clave):
  guardarlo en un lugar privado. La carpeta respaldos/ está en .gitignore: no subirlo al repo.

Sale con código 0 si el respaldo se hizo y el archivo se pudo leer con pg_restore --list.
"""
from __future__ import annotations  # `str | None` en las firmas: sin esto falla al importar en Python 3.9

import argparse
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlsplit, urlunsplit

MVP_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DIR = MVP_DIR / "respaldos"


def libpq_url_and_password(url: str) -> tuple[str, str | None]:
    """
    URL del backend (postgres://, postgresql://, postgresql+psycopg2://) -> (URL para libpq SIN
    clave, clave). Los parámetros (?sslmode=require, channel_binding, …) se conservan.
    """
    url = url.strip()
    parts = urlsplit(url)
    scheme = parts.scheme.split("+", 1)[0]
    if scheme not in ("postgres", "postgresql"):
        raise ValueError("DATABASE_URL no es una URL de PostgreSQL (postgres:// o postgresql://).")
    password = unquote(parts.password) if parts.password is not None else None
    netloc = parts.netloc.rsplit("@", 1)[-1]
    if parts.username is not None:
        netloc = f"{parts.username}@{netloc}"
    return urlunsplit(("postgresql", netloc, parts.path, parts.query, "")), password


def redact(url: str) -> str:
    """postgresql://usuario:clave@host/base?x -> postgresql://usuario:***@host/base?x (para mostrar)."""
    parts = urlsplit(url.strip())
    if parts.password is None:
        return url
    host = parts.netloc.rsplit("@", 1)[-1]
    return urlunsplit((parts.scheme, f"{parts.username}:***@{host}", parts.path, parts.query, ""))


def env_with_password(password: str | None) -> dict:
    env = dict(os.environ)
    env.pop("DATABASE_URL", None)  # el hijo no la necesita
    if password is not None:
        env["PGPASSWORD"] = password
    return env


def require_tool(name: str) -> str:
    path = shutil.which(name)
    if not path:
        sys.exit(f"No se encontró {name}. Instalar el cliente de PostgreSQL (ver docs/despliegue.md, 'Respaldos').")
    return path


def read_database_url() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        sys.exit("Falta la variable DATABASE_URL (la URL externa de la base; ver docs/despliegue.md).")
    return url


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", type=Path, default=DEFAULT_DIR, help=f"carpeta destino (default: {DEFAULT_DIR})")
    ap.add_argument("--prefijo", default="improntia", help="inicio del nombre del archivo (default: improntia)")
    args = ap.parse_args(argv)

    url = read_database_url()
    try:
        libpq_url, password = libpq_url_and_password(url)
    except ValueError as e:
        sys.exit(str(e))
    pg_dump = require_tool("pg_dump")
    pg_restore = require_tool("pg_restore")

    args.dir.mkdir(parents=True, exist_ok=True)
    destino = args.dir / f"{args.prefijo}_{datetime.now():%Y-%m-%d_%H%M}.dump"
    if destino.exists():
        destino = args.dir / f"{args.prefijo}_{datetime.now():%Y-%m-%d_%H%M%S}.dump"
    parcial = destino.with_suffix(".dump.parcial")

    version = subprocess.run([pg_dump, "--version"], capture_output=True, text=True).stdout.strip()
    print(f"Base:    {redact(url)}")
    print(f"Destino: {destino}")
    print(f"Usando:  {version}")

    # --no-owner / --no-privileges: el respaldo se puede restaurar en otro proveedor (otro usuario).
    r = subprocess.run(
        [pg_dump, "--format=custom", "--no-owner", "--no-privileges", f"--file={parcial}", f"--dbname={libpq_url}"],
        env=env_with_password(password), capture_output=True, text=True,
    )
    if r.returncode != 0:
        parcial.unlink(missing_ok=True)
        msg = r.stderr.strip()
        if password:
            msg = msg.replace(password, "***")
        print(f"\nFALLÓ pg_dump:\n{msg}", file=sys.stderr)
        if "version mismatch" in msg:
            print("-> Instalar un pg_dump de la misma versión que el servidor (o más nueva).", file=sys.stderr)
        return 1
    parcial.rename(destino)
    os.chmod(destino, 0o600)  # solo la persona que lo hizo puede leerlo

    # Comprobación: el archivo se puede leer y trae las tablas del backend.
    lista = subprocess.run([pg_restore, "--list", str(destino)], capture_output=True, text=True)
    tablas = sorted({line.split(" TABLE DATA ", 1)[1].split()[1]  # "…; 0 16390 TABLE DATA public users dueño"
                     for line in lista.stdout.splitlines() if " TABLE DATA " in line and not line.startswith(";")})
    if lista.returncode != 0 or "users" not in tablas:
        print(f"\nEl archivo se generó pero no parece un respaldo completo de ImprontIA (tablas: {tablas}).", file=sys.stderr)
        return 1
    kb = destino.stat().st_size / 1024
    print(f"\nRESPALDO OK — {destino.name} ({kb:,.0f} KB, {len(tablas)} tablas: {', '.join(tablas)})")
    print("Guardarlo en un lugar privado (contiene datos de estudiantes). Para restaurarlo: scripts/restaurar_base.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
