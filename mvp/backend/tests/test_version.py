"""
Paquete de reproducibilidad: identificador de versión inmutable (app/version.py).

GET /health y GET /version devuelven la versión de la entrega (archivo VERSION) y el commit
de git con el que se construyó (variable GIT_COMMIT; sin ella, "desconocido").
"""
import json
from pathlib import Path

from app import version as v

MVP = Path(__file__).resolve().parent.parent.parent


def test_version_file_default_and_dashboard_agree():
    archivo = (MVP / "VERSION").read_text(encoding="utf-8").strip()
    assert archivo == v.DEFAULT_VERSION == "1.0.0"
    paquete = json.loads((MVP / "dashboard" / "package.json").read_text(encoding="utf-8"))
    assert paquete["version"] == archivo


def test_version_sources_in_order():
    assert v.app_version({"APP_VERSION": "9.9.9"}) == "9.9.9"
    assert v.app_version({}) == "1.0.0"  # archivo VERSION
    assert v.git_commit({"GIT_COMMIT": " abc123 "}) == "abc123"
    assert v.git_commit({}) == v.UNKNOWN == "desconocido"
    assert v.git_commit({"GIT_COMMIT": ""}) == "desconocido"


def test_version_falls_back_to_default_without_file(monkeypatch, tmp_path):
    monkeypatch.setattr(v, "VERSION_FILES", (tmp_path / "VERSION",))
    assert v.app_version({}) == v.DEFAULT_VERSION


def test_health_and_version_endpoints(client, monkeypatch):
    monkeypatch.setenv("GIT_COMMIT", "0123456789abcdef0123456789abcdef01234567")
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["version"] == "1.0.0"
    assert body["commit"] == "0123456789abcdef0123456789abcdef01234567"
    assert client.get("/version").json() == {"version": "1.0.0", "commit": body["commit"]}
    monkeypatch.delenv("GIT_COMMIT")
    assert client.get("/version").json()["commit"] == "desconocido"


def test_dockerfile_keep_alive_and_commit_arg():
    df = (MVP / "backend" / "Dockerfile").read_text(encoding="utf-8")
    assert "--timeout-keep-alive 15" in df
    assert "ARG GIT_COMMIT" in df
