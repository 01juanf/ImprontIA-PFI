"""
Identificador de versión del MVP (paquete de reproducibilidad, entrega final).

- `version`: número de versión de la entrega. Se toma de APP_VERSION (si está definida), del
  archivo VERSION en la raíz de mvp/ (o en backend/, si se copia ahí) y, si no hay ninguno
  (por ejemplo, en la imagen Docker, cuyo contexto es solo backend/), de DEFAULT_VERSION. Un
  test verifica que DEFAULT_VERSION coincida con el archivo VERSION.
- `commit`: hash del commit de git con el que se construyó, desde la variable GIT_COMMIT
  (build arg de Docker / variable del hosting) o, en Vercel, de VERCEL_GIT_COMMIT_SHA; sin ella, "desconocido". No se consulta git en
  tiempo de ejecución: la imagen desplegada no tiene el repositorio.
"""
import os
from pathlib import Path
from typing import Mapping, Optional

DEFAULT_VERSION = "1.0.0"
UNKNOWN = "desconocido"

_BACKEND = Path(__file__).resolve().parent.parent
VERSION_FILES = (_BACKEND.parent / "VERSION", _BACKEND / "VERSION")


def app_version(env: Optional[Mapping[str, str]] = None) -> str:
    e = os.environ if env is None else env
    value = e.get("APP_VERSION", "").strip()
    if value:
        return value
    for path in VERSION_FILES:
        try:
            text = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if text:
            return text.splitlines()[0].strip()
    return DEFAULT_VERSION


def git_commit(env: Optional[Mapping[str, str]] = None) -> str:
    e = os.environ if env is None else env
    # GIT_COMMIT: build arg de Docker / variable puesta a mano. VERCEL_GIT_COMMIT_SHA: la expone
    # Vercel en cada despliegue desde Git (nov. 2026).
    value = e.get("GIT_COMMIT", "").strip() or e.get("VERCEL_GIT_COMMIT_SHA", "").strip()
    return value or UNKNOWN


def version_info(env: Optional[Mapping[str, str]] = None) -> dict:
    return {"version": app_version(env), "commit": git_commit(env)}
