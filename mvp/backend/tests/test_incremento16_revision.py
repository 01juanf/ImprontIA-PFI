"""
Revisión del código del Incremento 16 (21/10): una prueba por cada corrección.

- Cierre de la evaluación reclamado de forma atómica; si el análisis falla, se reabre.
- Un procesamiento concurrente/repetido de la misma sesión no la reprocesa ni duplica datos.
- La respuesta solo se guarda en la entrega (no en un /end posterior).
- La purga aplica el tope de 12 meses a políticas sin plazo y a sesiones abandonadas.
- Los números no finitos (NaN/Infinity) se rechazan en la validación de eventos.
"""
import json
from datetime import timedelta

from app import models
from app.database import SessionLocal
from app.processing.event_schema import validate_batch
from app.retention import purge_expired
from tests.test_incremento16 import H, _exam, _send_session, _start


def test_close_is_claimed_once_and_reopens_if_the_analysis_fails(client, teacher_token, monkeypatch):
    exam = _exam(client, teacher_token)
    for i in range(3):
        _send_session(client, exam, 80, 150, 0.5, 200 + i)

    from app.routers import exams as router
    calls = []

    def boom(metrics):
        calls.append(len(metrics))
        raise RuntimeError("falla simulada del análisis")

    monkeypatch.setattr(router, "analizar_cohorte", boom)
    r = client.post(f"/exams/{exam['id']}/cerrar", headers=H(teacher_token))
    assert r.status_code == 503
    # La evaluación sigue abierta: admite sesiones y el cierre se puede reintentar.
    assert client.get(f"/exams/{exam['id']}", headers=H(teacher_token)).json()["cerrada_at"] is None
    _start(client, exam, "TARDE")

    monkeypatch.undo()
    real = router.analizar_cohorte

    def counting(metrics):
        calls.append(len(metrics))
        return real(metrics)

    monkeypatch.setattr(router, "analizar_cohorte", counting)
    assert client.post(f"/exams/{exam['id']}/cerrar", headers=H(teacher_token)).status_code == 200
    # Un cierre que llega después (o mientras otro está en curso) no vuelve a analizar.
    db = SessionLocal()
    db.query(models.Exam).filter(models.Exam.id == exam["id"]).update({models.Exam.cerrada_at: models.utcnow()})
    db.commit()
    db.close()
    assert client.post(f"/exams/{exam['id']}/cerrar", headers=H(teacher_token)).status_code == 200
    assert calls == [3, 3]


def test_close_claim_is_conditional(client, teacher_token, monkeypatch):
    """Si otro request reclamó el cierre entre la lectura y el UPDATE, este no analiza."""
    exam = _exam(client, teacher_token)
    _send_session(client, exam, 80, 150, 0.5, 300)
    from app.routers import exams as router

    analyzed = []
    monkeypatch.setattr(router, "_analyze_cohort", lambda db, e: analyzed.append(e.id))

    # Simula la carrera: el examen se lee abierto, pero otro cierre lo reclama antes del UPDATE.
    db = SessionLocal()
    e = db.get(models.Exam, exam["id"])
    other = SessionLocal()
    other.query(models.Exam).filter(models.Exam.id == exam["id"]).update({models.Exam.cerrada_at: models.utcnow()})
    other.commit()
    other.close()
    assert e.cerrada_at is None  # vista desactualizada
    teacher = db.get(models.User, e.teacher_id)
    out = router.close_exam(exam["id"], db=db, teacher=teacher)
    assert out.cerrada_at is not None
    db.close()
    assert analyzed == []


def test_processing_is_not_repeated_for_an_already_processed_session(client, teacher_token):
    exam = _exam(client, teacher_token, signals=("keyboard", "clipboard"))
    sid, h = _start(client, exam)
    client.post(f"/sessions/{sid}/events", headers=h, json={"seq": 1, "events": [
        {"t": 0, "type": "keydown"}, {"t": 80, "type": "keyup", "dwell": 80},
        {"t": 100, "type": "paste", "chars": 900}]})

    from app.routers.sessions import process_session

    stale_db = SessionLocal()
    stale = stale_db.get(models.Session, sid)
    stale.status  # carga la fila
    assert client.post(f"/sessions/{sid}/end", headers=h).status_code == 200  # otro request la procesa
    ind = client.get(f"/sessions/{sid}", headers=H(teacher_token)).json()["indicators"][0]
    client.post(f"/sessions/{sid}/reviews", headers=H(teacher_token),
                json={"action": "marked_reviewed", "indicator_ids": [ind["id"]]})

    db = SessionLocal()
    before = sorted(m.id for m in db.query(models.Metric).filter(models.Metric.session_id == sid))
    links = db.query(models.ReviewIndicator).filter(models.ReviewIndicator.indicator_id == ind["id"]).count()
    db.close()
    assert stale.procesada_at is None  # el objeto viejo todavía no lo sabe
    assert process_session(stale_db, stale) is True
    stale_db.close()

    db = SessionLocal()
    after = sorted(m.id for m in db.query(models.Metric).filter(models.Metric.session_id == sid))
    assert after == before  # no se reprocesó ni se duplicó
    assert db.query(models.ReviewIndicator).filter(models.ReviewIndicator.indicator_id == ind["id"]).count() == links == 1
    db.close()


def test_answer_is_only_stored_at_submission(client, teacher_token):
    exam = _exam(client, teacher_token, signals=("keyboard",))
    sid, h = _start(client, exam)
    assert client.post(f"/sessions/{sid}/end", headers=h).status_code == 200
    assert client.post(f"/sessions/{sid}/end", headers=h, json={"respuesta": "entrega tardía"}).status_code == 200
    assert client.get(f"/sessions/{sid}", headers=H(teacher_token)).json()["respuesta"] is None


def test_purge_applies_the_12_month_cap_to_policies_without_a_term_and_to_abandoned_sessions(client, teacher_token):
    exam = _exam(client, teacher_token, signals=("keyboard",))  # sin retencion_dias
    old, h1 = _start(client, exam, "OLD")
    recent, h2 = _start(client, exam, "RECENT")
    abandoned, _ = _start(client, exam, "ABANDONADA")  # nunca se finaliza
    for s, h in ((old, h1), (recent, h2)):
        client.post(f"/sessions/{s}/end", headers=h)
    db = SessionLocal()
    db.get(models.Session, old).ended_at -= timedelta(days=models.RETENCION_MAX_DIAS + 1)
    db.get(models.Session, recent).ended_at -= timedelta(days=models.RETENCION_MAX_DIAS - 1)
    db.get(models.Session, abandoned).started_at -= timedelta(days=models.RETENCION_MAX_DIAS + 1)
    db.commit()
    assert purge_expired(db) >= 2
    assert db.get(models.Session, old) is None
    assert db.get(models.Session, abandoned) is None
    assert db.get(models.Session, recent) is not None
    db.close()


def test_non_finite_numbers_are_rejected(client, teacher_token):
    assert validate_batch([{"t": float("inf"), "type": "keydown"}], ["keyboard"])
    assert validate_batch([{"t": 0, "type": "mousemove", "x": float("nan"), "y": 0}], ["mouse"])
    assert validate_batch([{"t": 0, "type": "keyup", "dwell": float("inf")}], ["keyboard"])
    exam = _exam(client, teacher_token, signals=("mouse",))
    sid, h = _start(client, exam)
    body = json.dumps({"seq": 1, "events": [{"t": 0, "type": "mousemove", "x": float("inf"), "y": 0}]})
    r = client.post(f"/sessions/{sid}/events", headers={**h, "Content-Type": "application/json"}, content=body)
    assert r.status_code == 422


# ---- Pedidos del agente del dashboard (revisión del 21/10) ----

def test_seed_teacher_uses_migrations_and_old_create_all_dbs_are_healed(tmp_path):
    import os
    import subprocess
    import sys

    from sqlalchemy import create_engine

    from app.database import Base
    from app.db_migrations import HEAD_REVISION, current_revision, upgrade_db

    # 1) seed_teacher sobre una base vacía y DESPUÉS el arranque del backend (upgrade).
    url = f"sqlite:///{tmp_path / 'seed.db'}"
    env = {**os.environ, "DATABASE_URL": url}
    subprocess.run([sys.executable, "-m", "scripts.seed_teacher", "d@uade.edu.ar", "1234"], env=env, check=True,
                   cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))), capture_output=True)
    eng = create_engine(url)
    assert current_revision(eng) == HEAD_REVISION
    assert upgrade_db(eng) == "upgrade"
    eng.dispose()

    # 2) Una base que el seed_teacher viejo creó con create_all (esquema actual, sin
    # alembic_version) se marca en head en vez de fallar con columnas duplicadas.
    eng = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    Base.metadata.create_all(eng)
    assert upgrade_db(eng) == "stamp"
    assert current_revision(eng) == HEAD_REVISION
    eng.dispose()


def test_model_indicator_text_describes_the_cohort_analysis_at_close():
    from app.processing.cohort import analizar_cohorte
    from app.processing.indicators import indicator_from_anomaly
    from tests.test_incremento16 import _cohort

    draft = indicator_from_anomaly(analizar_cohorte(_cohort())["s999"])
    assert "ya registradas" not in draft.description
    assert "al cerrarla" in draft.description and "cohorte" in draft.description


def test_public_info_says_whether_the_exam_is_closed(client, teacher_token):
    exam = _exam(client, teacher_token, signals=("keyboard",))
    assert client.get(f"/exams/{exam['join_code']}/info").json()["cerrada"] is False
    client.post(f"/exams/{exam['id']}/cerrar", headers=H(teacher_token))
    assert client.get(f"/exams/{exam['join_code']}/info").json()["cerrada"] is True


def test_seed_demo_gives_synthetic_sessions_a_realistic_wall_duration(client, teacher_token):
    import os

    from scripts.seed_demo import MARGEN_MS, ajustar_duraciones

    exam = _exam(client, teacher_token, signals=("keyboard",))
    sid, h = _start(client, exam)
    client.post(f"/sessions/{sid}/end", headers=h)
    assert ajustar_duraciones(os.environ["DATABASE_URL"], {sid: 120_000.0}) == 1
    pan = client.get(f"/exams/{exam['id']}/panorama", headers=H(teacher_token)).json()
    wall = next(m for m in pan["metricas"] if m["metric"] == "session_wall_duration_ms")
    assert abs(wall["mediana"] - (120_000 + 2 * MARGEN_MS)) < 1


def test_connection_pool_covers_the_request_threadpool():
    """Con 200 entregas simultáneas, ningún request debe fallar por falta de conexión."""
    from anyio import to_thread

    from app.database import THREADPOOL_SIZE, engine

    assert to_thread.current_default_thread_limiter  # existe el limitador de hilos de anyio
    assert engine.pool.size() + engine.pool._max_overflow >= THREADPOOL_SIZE == 40


def test_concurrency_limit_caps_requests_in_flight():
    """Sin el límite, 200 /end simultáneos se bloqueaban entre hilos y conexiones (500)."""
    import asyncio

    import httpx

    from app.database import POOL_KWARGS, THREADPOOL_SIZE
    from app.main import MAX_REQUESTS_IN_FLIGHT, ConcurrencyLimit, app

    assert MAX_REQUESTS_IN_FLIGHT < THREADPOOL_SIZE
    assert MAX_REQUESTS_IN_FLIGHT < POOL_KWARGS["pool_size"] + POOL_KWARGS["max_overflow"]
    assert any(m.cls is ConcurrencyLimit for m in app.user_middleware)

    state = {"now": 0, "max": 0}

    async def inner(scope, receive, send):
        state["now"] += 1
        state["max"] = max(state["max"], state["now"])
        await asyncio.sleep(0.02)
        state["now"] -= 1
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    async def run():
        transport = httpx.ASGITransport(app=ConcurrencyLimit(inner, limit=3))
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            rs = await asyncio.gather(*[c.get("/") for _ in range(20)])
        assert all(r.status_code == 200 for r in rs)

    asyncio.run(run())
    assert state["max"] == 3


def test_session_list_query_count_does_not_grow_with_sessions(client, teacher_token):
    from sqlalchemy import event

    from app.database import engine

    exam = _exam(client, teacher_token, signals=("keyboard",))
    for i in range(6):
        sid, h = _start(client, exam, f"Q{i}")
        client.post(f"/sessions/{sid}/end", headers=h)
        client.post(f"/sessions/{sid}/reviews", headers=H(teacher_token), json={"action": "marked_reviewed"})
    statements = []

    def count(conn, cursor, statement, *a):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", count)
    try:
        r = client.get(f"/sessions?exam_id={exam['id']}", headers=H(teacher_token))
    finally:
        event.remove(engine, "before_cursor_execute", count)
    assert r.status_code == 200 and len(r.json()) == 6
    assert all(s["review_status"] == "revisada" and s["exam_name"] == "Inc16" for s in r.json())
    assert len(statements) <= 5  # docente + sesiones + revisiones (+ docentes de las revisiones)
