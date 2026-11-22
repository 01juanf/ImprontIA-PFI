import os
import tempfile

import pytest

# Debe fijarse ANTES de importar app.database (lee la env var al importarse).
# Por defecto, SQLite temporal. Con TEST_DATABASE_URL (Fase 2, P01) la misma suite corre
# contra otra base, p. ej. PostgreSQL: TEST_DATABASE_URL=postgresql://user:pass@host/db pytest
_test_db_url = os.environ.get("TEST_DATABASE_URL")
if _test_db_url:
    os.environ["DATABASE_URL"] = _test_db_url
else:
    _tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    os.environ["DATABASE_URL"] = f"sqlite:///{_tmp_db.name}"
os.environ.pop("IMPRONTIA_ENV", None)  # los tests corren siempre en modo desarrollo
os.environ.pop("SEED_TEACHERS", None)

if _test_db_url:
    # Base de prueba limpia en cada corrida (las migraciones la recrean al importar app.main).
    from sqlalchemy import text  # noqa: E402

    from app import models as _models  # noqa: E402,F401  (registra las tablas en Base)
    from app.database import Base, engine  # noqa: E402

    Base.metadata.drop_all(bind=engine)
    with engine.begin() as _conn:
        _conn.execute(text("DROP TABLE IF EXISTS alembic_version"))

from fastapi.testclient import TestClient  # noqa: E402

from app.auth import hash_password  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import User  # noqa: E402


@pytest.fixture(scope="session")
def client():
    return TestClient(app)


@pytest.fixture()
def teacher_token(client):
    db = SessionLocal()
    email = "test-docente@uade.edu.ar"
    if not db.query(User).filter(User.email == email).first():
        db.add(User(email=email, password_hash=hash_password("1234")))
        db.commit()
    db.close()

    resp = client.post("/auth/login", json={"email": email, "password": "1234"})
    assert resp.status_code == 200
    return resp.json()["access_token"]
