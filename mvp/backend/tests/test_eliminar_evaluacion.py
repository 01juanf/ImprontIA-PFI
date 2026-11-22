"""
RF17: DELETE /exams/{id} elimina una evaluación propia con todo lo asociado (sesiones,
eventos, métricas, indicadores, revisiones y versiones de política) vía
retention.delete_exam_data. Solo el docente propietario puede hacerlo.
"""
from app import models
from app.auth import hash_password
from app.database import SessionLocal

from tests.test_incremento16 import H, _exam, _start


def _other_teacher(client, email="ajeno.eliminar@uade.edu.ar"):
    db = SessionLocal()
    if not db.query(models.User).filter(models.User.email == email).first():
        db.add(models.User(email=email, password_hash=hash_password("clave-ajena")))
        db.commit()
    db.close()
    return client.post("/auth/login", json={"email": email, "password": "clave-ajena"}).json()["access_token"]


def test_delete_exam_cascades_everything(client, teacher_token):
    exam = _exam(client, teacher_token, signals=("keyboard",))
    sid, h = _start(client, exam, "BORRAR-1")
    events = [
        {"t": 100 + 150 * i, "type": t, **({"dwell": 80} if t == "keyup" else {})}
        for i in range(10) for t in ("keydown", "keyup")]
    r = client.post(f"/sessions/{sid}/events", headers=h, json={"seq": 1, "events": events})
    assert r.status_code == 201, r.text
    assert client.post(f"/sessions/{sid}/end", headers=h, json={"respuesta": "r"}).status_code == 200
    r = client.post(f"/sessions/{sid}/reviews", headers=H(teacher_token), json={"action": "marked_reviewed"})
    assert r.status_code == 200, r.text

    db = SessionLocal()
    assert db.query(models.Event).filter(models.Event.session_id == sid).count() > 0
    assert db.query(models.Metric).filter(models.Metric.session_id == sid).count() > 0
    assert db.query(models.Review).filter(models.Review.session_id == sid).count() == 1
    db.close()

    assert client.delete(f"/exams/{exam['id']}", headers=H(teacher_token)).status_code == 204
    assert client.get(f"/exams/{exam['id']}", headers=H(teacher_token)).status_code == 404
    assert client.get(f"/sessions/{sid}", headers=H(teacher_token)).status_code == 404
    assert client.get(f"/exams/{exam['join_code']}/info").status_code == 404

    db = SessionLocal()
    assert db.query(models.Exam).filter(models.Exam.id == exam["id"]).count() == 0
    assert db.query(models.PolicyCapture).filter(models.PolicyCapture.exam_id == exam["id"]).count() == 0
    assert db.query(models.Session).filter(models.Session.id == sid).count() == 0
    for model in (models.Event, models.Metric, models.Indicator, models.Review):
        assert db.query(model).filter(model.session_id == sid).count() == 0
    db.close()
    # Repetir el borrado responde 404 (ya no existe).
    assert client.delete(f"/exams/{exam['id']}", headers=H(teacher_token)).status_code == 404


def test_delete_exam_only_by_owner(client, teacher_token):
    exam = _exam(client, teacher_token, signals=("keyboard",))
    otro = _other_teacher(client)
    assert client.delete(f"/exams/{exam['id']}", headers=H(otro)).status_code == 404
    assert client.delete(f"/exams/{exam['id']}").status_code in (401, 403)  # sin token
    assert client.get(f"/exams/{exam['id']}", headers=H(teacher_token)).status_code == 200
    # Las demás evaluaciones del docente no se tocan.
    otra = _exam(client, teacher_token, signals=("keyboard",))
    assert client.delete(f"/exams/{exam['id']}", headers=H(teacher_token)).status_code == 204
    assert client.get(f"/exams/{otra['id']}", headers=H(teacher_token)).status_code == 200


def test_delete_session_with_review(client, teacher_token):
    """Regresión: DELETE /sessions/{id} fallaba (StaleDataError, 500) si la sesión tenía revisiones."""
    exam = _exam(client, teacher_token, signals=("keyboard",))
    sid, h = _start(client, exam, "BORRAR-REV")
    client.post(f"/sessions/{sid}/end", headers=h)
    assert client.post(f"/sessions/{sid}/reviews", headers=H(teacher_token),
                       json={"action": "additional_validation", "notes": "n"}).status_code == 200
    assert client.delete(f"/sessions/{sid}", headers=H(teacher_token)).status_code == 204
    db = SessionLocal()
    assert db.query(models.Review).filter(models.Review.session_id == sid).count() == 0
    db.close()
