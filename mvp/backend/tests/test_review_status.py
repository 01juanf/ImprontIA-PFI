"""
RF11/HU08 (Incremento 8): estado de revisión derivado de las revisiones
(solo inserción) y vista de sesiones con validación adicional pendiente.
"""


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _exam(client, token, name):
    resp = client.post("/exams", headers=auth_headers(token), json={
        "name": name, "info_text": "i", "rules_text": "r", "prompt_text": "p", "allowed_signals": [],
    })
    assert resp.status_code == 200
    return resp.json()


def _finished_session(client, join_code, participant):
    s = client.post("/sessions/start", json={
        "exam_code": join_code, "participant_id": participant, "consent_given": True, "context": {},
    }).json()
    h = {"X-Session-Token": s["session_token"]}
    client.post(f"/sessions/{s['session_id']}/events", headers=h, json={"seq": 1, "events": [{"t": 0, "type": "paste", "chars": 999}]})
    client.post(f"/sessions/{s['session_id']}/end", headers=h)
    return s["session_id"]


def _review(client, token, session_id, action, notes=None):
    resp = client.post(f"/sessions/{session_id}/reviews", headers=auth_headers(token),
                       json={"action": action, "notes": notes, "indicator_ids": []})
    assert resp.status_code == 200
    return resp.json()


def test_review_status_follows_the_last_review_and_history_is_kept(client, teacher_token):
    exam = _exam(client, teacher_token, "Estado de revisión")
    sid = _finished_session(client, exam["join_code"], "P-ESTADO")

    detail = client.get(f"/sessions/{sid}", headers=auth_headers(teacher_token)).json()
    assert detail["review_status"] == "sin_revision"
    assert detail["reviews"] == []
    assert detail["exam_name"] == "Estado de revisión"

    _review(client, teacher_token, sid, "additional_validation", "citar a instancia oral")
    detail = client.get(f"/sessions/{sid}", headers=auth_headers(teacher_token)).json()
    assert detail["review_status"] == "validacion_pendiente"
    assert detail["last_review_notes"] == "citar a instancia oral"

    # Una revisión posterior cierra el pedido, pero NO borra el registro anterior (solo inserción).
    _review(client, teacher_token, sid, "marked_reviewed", "oral rendida, sin observaciones")
    detail = client.get(f"/sessions/{sid}", headers=auth_headers(teacher_token)).json()
    assert detail["review_status"] == "revisada"
    assert [r["action"] for r in detail["reviews"]] == ["additional_validation", "marked_reviewed"]
    assert detail["reviews"][0]["teacher_email"] == "test-docente@uade.edu.ar"


def test_pending_validation_view_lists_across_exams_only_pending_ones(client, teacher_token):
    exam_a = _exam(client, teacher_token, "Pendientes A")
    exam_b = _exam(client, teacher_token, "Pendientes B")
    pend_a = _finished_session(client, exam_a["join_code"], "P-PEND-A")
    pend_b = _finished_session(client, exam_b["join_code"], "P-PEND-B")
    closed = _finished_session(client, exam_a["join_code"], "P-CERRADA")
    untouched = _finished_session(client, exam_b["join_code"], "P-SIN-REVISAR")

    _review(client, teacher_token, pend_a, "additional_validation")
    _review(client, teacher_token, pend_b, "additional_validation")
    _review(client, teacher_token, closed, "additional_validation")
    _review(client, teacher_token, closed, "marked_reviewed")

    resp = client.get("/sessions", params={"review_status": "validacion_pendiente"}, headers=auth_headers(teacher_token))
    assert resp.status_code == 200
    ids = {s["id"] for s in resp.json()}
    assert {pend_a, pend_b} <= ids
    assert closed not in ids and untouched not in ids
    assert {s["exam_name"] for s in resp.json() if s["id"] in (pend_a, pend_b)} == {"Pendientes A", "Pendientes B"}

    # Combinable con el filtro por evaluación.
    only_a = client.get("/sessions", params={"review_status": "validacion_pendiente", "exam_id": exam_a["id"]},
                        headers=auth_headers(teacher_token)).json()
    assert {s["id"] for s in only_a} == {pend_a}

    sin_revision = client.get("/sessions", params={"review_status": "sin_revision", "exam_id": exam_b["id"]},
                              headers=auth_headers(teacher_token)).json()
    assert {s["id"] for s in sin_revision} == {untouched}


def test_invalid_review_status_filter_is_rejected(client, teacher_token):
    resp = client.get("/sessions", params={"review_status": "culpable"}, headers=auth_headers(teacher_token))
    assert resp.status_code == 400


def test_pending_view_does_not_leak_other_teachers_sessions(client, teacher_token):
    from app.auth import create_access_token, hash_password
    from app.database import SessionLocal
    from app.models import User

    exam = _exam(client, teacher_token, "Privado pendientes")
    sid = _finished_session(client, exam["join_code"], "P-PRIV")
    _review(client, teacher_token, sid, "additional_validation")

    db = SessionLocal()
    other = db.query(User).filter(User.email == "otro-docente-2@uade.edu.ar").first()
    if not other:
        other = User(email="otro-docente-2@uade.edu.ar", password_hash=hash_password("1234"))
        db.add(other)
        db.commit()
        db.refresh(other)
    token = create_access_token(other.id)
    db.close()

    resp = client.get("/sessions", params={"review_status": "validacion_pendiente"}, headers=auth_headers(token))
    assert resp.status_code == 200
    assert sid not in {s["id"] for s in resp.json()}
