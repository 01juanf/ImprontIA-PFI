"""
Fase 2, P02 (Incremento 14): migraciones con Alembic y campos del ER que faltaban
(`PolicyCapture.retencion_dias`, `Metric.evento_desde/hasta`, `Indicator.estado`).

Las pruebas de migración usan una base SQLite temporal propia; la de coincidencia
modelos <-> migraciones usa la base de la suite (SQLite o, con TEST_DATABASE_URL,
PostgreSQL), que conftest crea con las migraciones al importar app.main.
"""
import pytest
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text

from app.database import Base, engine as suite_engine
from app.db_migrations import (
    BASELINE_REVISION,
    HEAD_REVISION,
    current_revision,
    downgrade_db,
    upgrade_db,
)

NUEVAS = {
    "policy_captures": {"retencion_dias"},
    "metrics": {"evento_desde", "evento_hasta"},
    "indicators": {"estado"},
}


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _columns(engine, table: str) -> set[str]:
    return {c["name"] for c in inspect(engine).get_columns(table)}


@pytest.fixture()
def tmp_engine(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 'migr.db'}")
    yield eng
    eng.dispose()


def test_suite_db_is_at_head_and_matches_the_models():
    """El esquema que crean las migraciones es exactamente el de models.py (sin diferencias)."""
    assert current_revision(suite_engine) == HEAD_REVISION
    with suite_engine.connect() as conn:
        diffs = compare_metadata(MigrationContext.configure(conn, opts={"compare_type": True}), Base.metadata)
    assert diffs == []


def test_upgrade_and_downgrade_on_an_empty_db(tmp_engine):
    assert upgrade_db(tmp_engine) == "upgrade"
    assert current_revision(tmp_engine) == HEAD_REVISION
    for table, cols in NUEVAS.items():
        assert cols <= _columns(tmp_engine, table)

    downgrade_db(tmp_engine, BASELINE_REVISION)
    assert current_revision(tmp_engine) == BASELINE_REVISION
    for table, cols in NUEVAS.items():
        assert not (cols & _columns(tmp_engine, table))

    assert upgrade_db(tmp_engine) == "upgrade"  # y se puede volver a subir
    assert upgrade_db(tmp_engine) == "upgrade"  # idempotente: ya está en head
    assert current_revision(tmp_engine) == HEAD_REVISION


def test_db_created_before_p02_is_stamped_and_upgraded_keeping_its_data(tmp_engine):
    """Una base creada con create_all (sin alembic_version) se actualiza sin perder datos."""
    upgrade_db(tmp_engine, BASELINE_REVISION)  # mismo esquema que create_all antes de P02
    with tmp_engine.begin() as c:
        c.execute(text("DROP TABLE alembic_version"))
        c.execute(text("INSERT INTO users VALUES ('u1','d@x.com','h','docente',NULL)"))
        c.execute(text("INSERT INTO exams VALUES ('e1','u1','Ex','ABC123','',NULL)"))
        c.execute(text("INSERT INTO policy_captures VALUES ('p1','e1','i','r','[\"keyboard\"]',NULL)"))
        c.execute(text(
            "INSERT INTO sessions VALUES ('s1','e1','p1','P1','exam','ended','{}','tok',1,1,3,1,NULL,NULL)"))
        c.execute(text("INSERT INTO metrics VALUES ('m1','s1','paste_chars_total',999,NULL,NULL)"))
        c.execute(text("INSERT INTO indicators VALUES ('i1','s1','paste_volume_alto','medium','d','{}',NULL)"))
        c.execute(text("INSERT INTO indicators VALUES ('i2','s1','cambios_pestana_frecuentes','medium','d','{}',NULL)"))
        c.execute(text("INSERT INTO reviews VALUES ('r1','s1','u1','marked_reviewed',NULL,NULL)"))
        c.execute(text("INSERT INTO review_indicators VALUES ('ri1','r1','i1')"))

    assert upgrade_db(tmp_engine) == "stamp+upgrade"
    assert current_revision(tmp_engine) == HEAD_REVISION
    with tmp_engine.connect() as c:
        assert c.execute(text("SELECT email FROM users")).scalar_one() == "d@x.com"
        assert c.execute(text("SELECT retencion_dias FROM policy_captures")).scalar_one() is None
        assert c.execute(text("SELECT value, evento_desde, evento_hasta FROM metrics")).one() == (999, None, None)
        estados = dict(c.execute(text("SELECT id, estado FROM indicators")).all())
    # El indicador que ya citaba una revisión queda "atendido"; el otro, "pendiente".
    assert estados == {"i1": "atendido", "i2": "pendiente"}


def _exam(client, token, **extra):
    resp = client.post("/exams", headers=auth_headers(token), json={
        "name": "Retención", "info_text": "i", "rules_text": "r", "prompt_text": "p",
        "allowed_signals": ["keyboard", "clipboard"], **extra,
    })
    return resp


def test_retencion_dias_is_optional_and_bounded(client, teacher_token):
    default = _exam(client, teacher_token).json()
    assert default["current_policy"]["retencion_dias"] is None  # comportamiento anterior

    exam = _exam(client, teacher_token, retencion_dias=90).json()
    assert exam["current_policy"]["retencion_dias"] == 90
    for invalid in (0, 366, -5):
        assert _exam(client, teacher_token, retencion_dias=invalid).status_code == 422

    pol = client.post(f"/exams/{exam['id']}/policy", headers=auth_headers(teacher_token), json={
        "info_text": "i2", "rules_text": "r2", "allowed_signals": ["keyboard"], "retencion_dias": 365,
    }).json()
    assert pol["retencion_dias"] == 365
    sin_plazo = client.post(f"/exams/{exam['id']}/policy", headers=auth_headers(teacher_token), json={
        "info_text": "i3", "rules_text": "r3", "allowed_signals": ["keyboard"],
    }).json()
    assert sin_plazo["retencion_dias"] is None  # cada versión declara su propio plazo


def test_metrics_keep_their_event_range_and_reviews_mark_indicators_as_attended(client, teacher_token):
    exam = _exam(client, teacher_token).json()
    s = client.post("/sessions/start", json={
        "exam_code": exam["join_code"], "participant_id": "P-RANGO", "consent_given": True, "context": {},
    }).json()
    h = {"X-Session-Token": s["session_token"]}
    client.post(f"/sessions/{s['session_id']}/events", headers=h, json={"seq": 1, "events": [
        {"t": 0, "type": "keydown", "item_ref": "q1"}, {"t": 80, "type": "keyup", "item_ref": "q1"},
        {"t": 500, "type": "paste", "chars": 900, "item_ref": "q2"},
    ]})
    client.post(f"/sessions/{s['session_id']}/events", headers=h, json={"seq": 2, "events": [
        {"t": 900, "type": "keydown", "item_ref": "q2"}, {"t": 990, "type": "keyup", "item_ref": "q2"},
    ]})
    client.post(f"/sessions/{s['session_id']}/end", headers=h)

    detail = client.get(f"/sessions/{s['session_id']}", headers=auth_headers(teacher_token)).json()
    rangos = {(m["item_ref"], m["evento_desde"], m["evento_hasta"]) for m in detail["metrics"]}
    assert rangos == {(None, 0, 4), ("q1", 0, 1), ("q2", 2, 4)}

    ind = next(i for i in detail["indicators"] if i["kind"] == "paste_volume_alto")
    assert ind["estado"] == "pendiente"

    # Una revisión sin indicadores no cambia el estado; una que lo cita lo marca "atendido".
    client.post(f"/sessions/{s['session_id']}/reviews", headers=auth_headers(teacher_token),
                json={"action": "additional_validation", "indicator_ids": []})
    detail = client.get(f"/sessions/{s['session_id']}", headers=auth_headers(teacher_token)).json()
    assert {i["estado"] for i in detail["indicators"]} == {"pendiente"}

    client.post(f"/sessions/{s['session_id']}/reviews", headers=auth_headers(teacher_token),
                json={"action": "marked_reviewed", "indicator_ids": [ind["id"]]})
    detail = client.get(f"/sessions/{s['session_id']}", headers=auth_headers(teacher_token)).json()
    assert next(i for i in detail["indicators"] if i["id"] == ind["id"])["estado"] == "atendido"
    assert detail["review_status"] == "revisada"


def test_session_without_events_has_no_event_range(client, teacher_token):
    exam = _exam(client, teacher_token).json()
    s = client.post("/sessions/start", json={
        "exam_code": exam["join_code"], "participant_id": "P-VACIA", "consent_given": True, "context": {},
    }).json()
    client.post(f"/sessions/{s['session_id']}/end", headers={"X-Session-Token": s["session_token"]})
    detail = client.get(f"/sessions/{s['session_id']}", headers=auth_headers(teacher_token)).json()
    assert detail["metrics"] and all(m["evento_desde"] is None and m["evento_hasta"] is None for m in detail["metrics"])
