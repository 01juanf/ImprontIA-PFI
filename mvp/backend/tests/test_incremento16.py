"""
Incremento 16: correcciones de la revisión externa.

- Validación de eventos en el servidor según la política de la sesión.
- Duración de pulsación emparejada en el navegador (sin enviar la tecla).
- Análisis poblacional al cierre de la evaluación, invariante al orden de entrega.
- Cierre de sesión idempotente, procesamiento recuperable y entrega de la respuesta.
- Eliminación de sesiones y cuentas (RF17) y purga por vencimiento (RNF10).
"""
import random
from datetime import timedelta

from sqlalchemy import create_engine, inspect

from app import models
from app.database import SessionLocal
from app.db_migrations import HEAD_REVISION, current_revision, downgrade_db, upgrade_db
from app.processing.cohort import analizar_cohorte
from app.processing.event_schema import validate_batch
from app.processing.features import compute_keystroke_features
from app.retention import purge_expired


def H(token):
    return {"Authorization": f"Bearer {token}"}


def _exam(client, token, signals=("keyboard", "mouse"), **extra):
    r = client.post("/exams", headers=H(token), json={
        "name": "Inc16", "prompt_text": "p", "info_text": "i", "rules_text": "r",
        "allowed_signals": list(signals), **extra})
    assert r.status_code == 200, r.text
    return r.json()


def _start(client, exam, pid="P"):
    r = client.post("/sessions/start", json={"exam_code": exam["join_code"], "participant_id": pid,
                                             "consent_given": True, "context": {}})
    assert r.status_code == 200, r.text
    s = r.json()
    return s["session_id"], {"X-Session-Token": s["session_token"]}


# ---- Validación de eventos en el servidor ----

def test_validate_batch_rules():
    ok = [{"t": 0, "type": "keydown"}, {"t": 80, "type": "keyup", "dwell": 80},
          {"t": 90, "type": "sync_failure", "failed_attempts": 3, "duration_ms": 1000}]
    assert validate_batch(ok, ["keyboard"]) == []
    assert validate_batch([{"t": 0, "type": "keydown", "code": "KeyA"}], ["keyboard"])  # identidad de la tecla
    assert validate_batch([{"t": 0, "type": "paste", "chars": 10}], ["keyboard"])  # categoría no habilitada
    assert validate_batch([{"t": 0, "type": "keylogger"}], ["keyboard"])  # tipo desconocido
    assert validate_batch([{"t": -5, "type": "keydown"}], ["keyboard"])  # valor inválido
    assert validate_batch([{"t": 0, "type": "paste", "chars": "mucho"}], ["clipboard"])
    assert validate_batch([{"t": 0, "type": "paste", "chars": 3, "text": "hola"}], ["clipboard"])  # contenido


def test_api_rejects_events_outside_the_session_policy(client, teacher_token):
    exam = _exam(client, teacher_token, signals=("keyboard",))
    sid, h = _start(client, exam)
    for bad in ([{"t": 0, "type": "keydown", "code": "KeyA"}],
                [{"t": 0, "type": "mousemove", "x": 1, "y": 1}],
                [{"t": 0, "type": "paste", "chars": 500}]):
        r = client.post(f"/sessions/{sid}/events", headers=h, json={"seq": 1, "events": bad})
        assert r.status_code == 422
    r = client.post(f"/sessions/{sid}/events", headers=h, json={"seq": 1, "events": [
        {"t": 0, "type": "keydown"}, {"t": 70, "type": "keyup", "dwell": 70}]})
    assert r.status_code == 201
    db = SessionLocal()
    assert db.query(models.Event).filter(models.Event.session_id == sid).count() == 2
    db.close()


# ---- Teclado: emparejamiento en el navegador ----

def test_client_paired_dwell_with_overlapping_keys():
    # A abajo (0), B abajo (30), A arriba (100), B arriba (110): A dura 100 y B 80.
    # El navegador empareja por tecla y envía la duración; el orden de llegada daría lo mismo
    # en este caso, pero si se libera primero la tecla presionada después, FIFO intercambia.
    swapped = [{"t": 0, "type": "keydown"}, {"t": 30, "type": "keydown"},
               {"t": 60, "type": "keyup"}, {"t": 120, "type": "keyup"}]  # B (30-60) suelta antes que A (0-120)
    fifo = compute_keystroke_features(swapped)
    paired = compute_keystroke_features([
        {"t": 0, "type": "keydown"}, {"t": 30, "type": "keydown"},
        {"t": 60, "type": "keyup", "dwell": 30}, {"t": 120, "type": "keyup", "dwell": 120}])
    assert paired["mean_dwell_time_ms"] == 75 and paired["std_dwell_time_ms"] == 45
    assert fifo["std_dwell_time_ms"] != paired["std_dwell_time_ms"]  # FIFO: 60 y 90 -> desvío 15
    # Liberación sin pulsación registrada (p. ej. tras volver el foco): no aporta duración.
    unpaired = compute_keystroke_features([{"t": 0, "type": "keyup", "dwell": None},
                                           {"t": 10, "type": "keydown"}, {"t": 90, "type": "keyup", "dwell": 80}])
    assert unpaired["mean_dwell_time_ms"] == 80


# ---- Análisis poblacional al cierre ----

def _cohort(n=30, seed=1):
    rng = random.Random(seed)
    data = {f"s{i:03d}": {"mean_dwell_time_ms": rng.gauss(95, 10), "std_dwell_time_ms": rng.gauss(20, 3),
                           "mean_flight_time_ms": rng.gauss(160, 20), "mean_mouse_speed_px_ms": rng.gauss(0.6, 0.1),
                           "std_mouse_speed_px_ms": rng.gauss(0.2, 0.03)} for i in range(n)}
    data["s999"] = {"mean_dwell_time_ms": 300, "std_dwell_time_ms": 60, "mean_flight_time_ms": 500,
                    "mean_mouse_speed_px_ms": 3.0, "std_mouse_speed_px_ms": 1.0}
    return data


def test_cohort_analysis_does_not_depend_on_arrival_order():
    data = _cohort()
    base = analizar_cohorte(data)
    keys = list(data)
    for seed in range(3):
        random.Random(seed).shuffle(keys)
        again = analizar_cohorte({k: data[k] for k in keys})
        assert {k: (r.is_anomalous, round(r.anomaly_score, 12)) for k, r in again.items()} == \
               {k: (r.is_anomalous, round(r.anomaly_score, 12)) for k, r in base.items()}
    assert base["s999"].is_anomalous
    assert all(r is None for r in analizar_cohorte(dict(list(data.items())[:10])).values())


def _send_session(client, exam, dwell, gap, speed, seed):
    sid, h = _start(client, exam, f"P{seed}")
    ev, t = [], 0
    for k in range(40):
        d, g = dwell + (seed + k) % 11, gap + (seed + 3 * k) % 17
        ev += [{"t": t, "type": "keydown"}, {"t": t + d, "type": "keyup", "dwell": d},
               {"t": t + d + 10, "type": "mousemove", "x": k * speed, "y": 0},
               {"t": t + d + 110, "type": "mousemove", "x": k * speed + speed * 10, "y": 0}]
        t += d + g
    assert client.post(f"/sessions/{sid}/events", headers=h, json={"seq": 1, "events": ev}).status_code == 201
    assert client.post(f"/sessions/{sid}/end", headers=h).json()["procesada"] is True
    return sid


def test_close_exam_analyzes_the_whole_cohort(client, teacher_token):
    exam = _exam(client, teacher_token)
    ids = [_send_session(client, exam, 80, 150, 0.5, i) for i in range(21)]
    outlier = _send_session(client, exam, 300, 500, 3.0, 99)
    pan = client.get(f"/exams/{exam['id']}/panorama", headers=H(teacher_token)).json()
    assert pan["cobertura"] == {"evaluacion_cerrada": False, "sesiones_evaluadas": 0,
                                "sesiones_no_evaluadas": 0, "sesiones_pendientes": 22}
    r = client.post(f"/exams/{exam['id']}/cerrar", headers=H(teacher_token))
    assert r.status_code == 200
    estados = {s["id"]: s["estado_modelo"] for s in
               client.get(f"/sessions?exam_id={exam['id']}", headers=H(teacher_token)).json()}
    assert estados[outlier] == "con_marca"
    assert set(estados.values()) <= {"con_marca", "sin_marca"} and len(estados) == 22
    pan = client.get(f"/exams/{exam['id']}/panorama", headers=H(teacher_token)).json()
    assert pan["cobertura"]["evaluacion_cerrada"] and pan["cobertura"]["sesiones_evaluadas"] == 22
    # Cerrada: no admite sesiones nuevas y repetir el cierre no cambia nada.
    assert client.post("/sessions/start", json={"exam_code": exam["join_code"], "participant_id": "X",
                                                "consent_given": True}).status_code == 409
    assert client.post(f"/exams/{exam['id']}/cerrar", headers=H(teacher_token)).status_code == 200
    assert ids  # (las 21 normales quedaron evaluadas)


def test_small_cohort_is_marked_not_evaluated(client, teacher_token):
    exam = _exam(client, teacher_token)
    sid = _send_session(client, exam, 80, 150, 0.5, 1)
    client.post(f"/exams/{exam['id']}/cerrar", headers=H(teacher_token))
    d = client.get(f"/sessions/{sid}", headers=H(teacher_token)).json()
    assert d["estado_modelo"] == "no_evaluada"


# ---- Cierre de sesión ----

def test_end_is_idempotent_stores_the_answer_and_recovers_failed_processing(client, teacher_token, monkeypatch):
    exam = _exam(client, teacher_token, signals=("keyboard",))
    sid, h = _start(client, exam)
    client.post(f"/sessions/{sid}/events", headers=h, json={"seq": 1, "events": [
        {"t": 0, "type": "keydown"}, {"t": 80, "type": "keyup", "dwell": 80}]})

    from app.routers import sessions as router

    def boom(_events):
        raise RuntimeError("falla simulada del procesamiento")

    monkeypatch.setattr(router, "compute_all_features", boom)
    r = client.post(f"/sessions/{sid}/end", headers=h, json={"respuesta": "Mi respuesta"})
    assert r.status_code == 503
    d = client.get(f"/sessions/{sid}", headers=H(teacher_token)).json()
    assert d["status"] == "ended" and d["procesada"] is False and d["respuesta"] == "Mi respuesta"

    monkeypatch.undo()
    r = client.post(f"/sessions/{sid}/end", headers=h)  # reintento seguro
    assert r.status_code == 200 and r.json()["procesada"] is True
    again = client.post(f"/sessions/{sid}/end", headers=h)
    assert again.status_code == 200 and again.json() == r.json()
    d = client.get(f"/sessions/{sid}", headers=H(teacher_token)).json()
    assert d["procesada"] is True and d["metrics"] and d["respuesta"] == "Mi respuesta"


# ---- Eliminación y retención ----

def test_delete_session_and_account(client, teacher_token):
    exam = _exam(client, teacher_token, signals=("keyboard",))
    sid, h = _start(client, exam)
    client.post(f"/sessions/{sid}/events", headers=h, json={"seq": 1, "events": [{"t": 0, "type": "keydown"}]})
    client.post(f"/sessions/{sid}/end", headers=h)
    assert client.delete(f"/sessions/{sid}", headers=H(teacher_token)).status_code == 204
    assert client.get(f"/sessions/{sid}", headers=H(teacher_token)).status_code == 404
    db = SessionLocal()
    assert db.query(models.Event).filter(models.Event.session_id == sid).count() == 0
    assert db.query(models.Metric).filter(models.Metric.session_id == sid).count() == 0
    db.close()

    # Cuenta: se crea un docente aparte para no borrar el de la suite.
    from app.auth import hash_password
    db = SessionLocal()
    db.add(models.User(email="borrar@uade.edu.ar", password_hash=hash_password("clave-123")))
    db.commit()
    db.close()
    tok = client.post("/auth/login", json={"email": "borrar@uade.edu.ar", "password": "clave-123"}).json()["access_token"]
    own = _exam(client, tok, signals=("keyboard",))
    s2, h2 = _start(client, own)
    client.post(f"/sessions/{s2}/end", headers=h2)
    assert client.request("DELETE", "/auth/me", headers=H(tok), json={"password": "otra"}).status_code == 401
    assert client.request("DELETE", "/auth/me", headers=H(tok), json={"password": "clave-123"}).status_code == 204
    db = SessionLocal()
    assert db.query(models.User).filter(models.User.email == "borrar@uade.edu.ar").first() is None
    assert db.query(models.Exam).filter(models.Exam.id == own["id"]).first() is None
    assert db.query(models.Session).filter(models.Session.id == s2).first() is None
    db.close()


def test_purge_removes_only_expired_sessions(client, teacher_token):
    exam = _exam(client, teacher_token, signals=("keyboard",), retencion_dias=30)
    old, h1 = _start(client, exam, "OLD")
    new, h2 = _start(client, exam, "NEW")
    for s, h in ((old, h1), (new, h2)):
        client.post(f"/sessions/{s}/end", headers=h)
    db = SessionLocal()
    db.get(models.Session, old).ended_at -= timedelta(days=31)
    db.commit()
    assert purge_expired(db) >= 1
    assert db.get(models.Session, old) is None and db.get(models.Session, new) is not None
    db.close()


def test_migration_0004_up_and_down(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 'm4.db'}")
    upgrade_db(eng)
    assert current_revision(eng) == HEAD_REVISION == "0005_ejercicios_y_pdf"
    cols = {c["name"] for c in inspect(eng).get_columns("sessions")}
    assert {"procesada_at", "estado_modelo", "respuesta"} <= cols
    downgrade_db(eng, "0003_condicion_simulacion")
    assert "respuesta" not in {c["name"] for c in inspect(eng).get_columns("sessions")}
    upgrade_db(eng)
    eng.dispose()
