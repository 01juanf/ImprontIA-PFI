"""
Prueba de integración mínima del flujo completo (cap. 15: "creación de sesión,
recepción de eventos, consulta de indicadores"): crear examen -> iniciar sesión
-> enviar eventos -> finalizar -> consultar detalle con indicadores.
"""


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_public_exam_info_visible_before_consent(client, teacher_token):
    """RF01/RF02: el estudiante debe poder ver info y reglas antes de aceptar, sin login."""
    exam_resp = client.post(
        "/exams",
        headers=auth_headers(teacher_token),
        json={
            "name": "Final de Bases de Datos",
            "info_text": "Se registra teclado y mouse.",
            "rules_text": "Libro abierto, sin conexión a internet.",
            "prompt_text": "Consigna de prueba.",
            "allowed_signals": ["keyboard", "mouse"],
        },
    )
    join_code = exam_resp.json()["join_code"]

    resp = client.get(f"/exams/{join_code}/info")
    assert resp.status_code == 200
    body = resp.json()
    assert body["info_text"] == "Se registra teclado y mouse."
    assert body["rules_text"] == "Libro abierto, sin conexión a internet."
    assert "id" not in body  # no debe filtrar el id interno del examen
    assert "prompt_text" not in body  # la consigna no se revela antes de consentir/iniciar

    assert client.get("/exams/NOEXISTE/info").status_code == 404


def test_prompt_text_revealed_only_after_session_start(client, teacher_token):
    exam_resp = client.post(
        "/exams",
        headers=auth_headers(teacher_token),
        json={
            "name": "Con consigna",
            "info_text": "i",
            "rules_text": "r",
            "prompt_text": "Desarrolle el tema X.",
            "allowed_signals": [],
        },
    )
    exam_code = exam_resp.json()["join_code"]

    start_resp = client.post(
        "/sessions/start",
        json={"exam_code": exam_code, "participant_id": "P1", "consent_given": True, "context": {}},
    )
    assert start_resp.json()["prompt_text"] == "Desarrolle el tema X."


def test_full_session_lifecycle(client, teacher_token):
    exam_resp = client.post(
        "/exams",
        headers=auth_headers(teacher_token),
        json={
            "name": "Parcial de prueba",
            "info_text": "info",
            "rules_text": "reglas",
            "prompt_text": "Resolvé el ejercicio 3.",
            "allowed_signals": ["keyboard", "clipboard"],
        },
    )
    assert exam_resp.status_code == 200
    exam_code = exam_resp.json()["join_code"]

    start_resp = client.post(
        "/sessions/start",
        json={
            "exam_code": exam_code,
            "participant_id": "EST-TEST",
            "session_type": "exam",
            "context": {},
            "consent_given": True,
        },
    )
    assert start_resp.status_code == 200
    body = start_resp.json()
    session_id, session_token = body["session_id"], body["session_token"]

    events_resp = client.post(
        f"/sessions/{session_id}/events",
        headers={"X-Session-Token": session_token},
        json={"seq": 1, "events": [{"t": 0, "type": "paste", "chars": 999}]},
    )
    assert events_resp.status_code == 201

    end_resp = client.post(f"/sessions/{session_id}/end", headers={"X-Session-Token": session_token})
    assert end_resp.status_code == 200
    assert end_resp.json()["needs_review"] is True

    detail_resp = client.get(f"/sessions/{session_id}", headers=auth_headers(teacher_token))
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["needs_review"] is True
    assert any(i["kind"] == "paste_volume_alto" for i in detail["indicators"])
    assert detail["event_count"] == 1


def test_duplicate_event_batch_is_not_double_inserted(client, teacher_token):
    """
    Idempotencia de red (EventBatchIn.seq): si el cliente reintenta un lote porque
    no recibió la confirmación a tiempo (típico en una conexión inestable durante
    un examen real), el backend no debe duplicar los eventos ya guardados.
    """
    exam_resp = client.post(
        "/exams",
        headers=auth_headers(teacher_token),
        json={
            "name": "Reintento de red",
            "info_text": "info",
            "rules_text": "reglas",
            "prompt_text": "p",
            "allowed_signals": ["keyboard"],
        },
    )
    exam_code = exam_resp.json()["join_code"]

    start_resp = client.post(
        "/sessions/start",
        json={"exam_code": exam_code, "participant_id": "EST-RETRY", "consent_given": True, "context": {}},
    )
    session_id, session_token = start_resp.json()["session_id"], start_resp.json()["session_token"]
    headers = {"X-Session-Token": session_token}
    batch = {"seq": 1, "events": [{"t": 0, "type": "keydown"}, {"t": 50, "type": "keyup"}]}

    first = client.post(f"/sessions/{session_id}/events", headers=headers, json=batch)
    assert first.status_code == 201
    assert first.json()["stored"] == 2

    # El cliente no vio la respuesta a tiempo y reintenta el mismo lote (mismo seq).
    retry = client.post(f"/sessions/{session_id}/events", headers=headers, json=batch)
    assert retry.status_code == 201
    assert retry.json()["stored"] == 0  # idempotente: no vuelve a insertar

    # Un lote siguiente (seq mayor) sí se aplica con normalidad.
    next_batch = {"seq": 2, "events": [{"t": 100, "type": "keydown"}]}
    third = client.post(f"/sessions/{session_id}/events", headers=headers, json=next_batch)
    assert third.status_code == 201
    assert third.json()["stored"] == 1

    end_resp = client.post(f"/sessions/{session_id}/end", headers=headers)
    assert end_resp.status_code == 200

    detail = client.get(f"/sessions/{session_id}", headers=auth_headers(teacher_token)).json()
    assert detail["event_count"] == 3  # 2 del primer lote (una sola vez) + 1 del segundo, no 5


def test_session_start_requires_consent(client, teacher_token):
    exam_resp = client.post(
        "/exams",
        headers=auth_headers(teacher_token),
        json={"name": "X", "info_text": "i", "rules_text": "r", "prompt_text": "p", "allowed_signals": []},
    )
    exam_code = exam_resp.json()["join_code"]

    resp = client.post(
        "/sessions/start",
        json={"exam_code": exam_code, "participant_id": "P1", "consent_given": False, "context": {}},
    )
    assert resp.status_code == 400


def test_events_rejected_with_wrong_session_token(client, teacher_token):
    exam_resp = client.post(
        "/exams",
        headers=auth_headers(teacher_token),
        json={"name": "X", "info_text": "i", "rules_text": "r", "prompt_text": "p", "allowed_signals": []},
    )
    exam_code = exam_resp.json()["join_code"]
    start_resp = client.post(
        "/sessions/start",
        json={"exam_code": exam_code, "participant_id": "P1", "consent_given": True, "context": {}},
    )
    session_id = start_resp.json()["session_id"]

    resp = client.post(
        f"/sessions/{session_id}/events",
        headers={"X-Session-Token": "token-incorrecto"},
        json={"seq": 1, "events": []},
    )
    assert resp.status_code == 401


def test_teacher_cannot_see_another_teachers_session(client, teacher_token):
    """RNF03/Seguridad: un docente no debe poder consultar sesiones ajenas."""
    exam_resp = client.post(
        "/exams",
        headers=auth_headers(teacher_token),
        json={"name": "Privado", "info_text": "i", "rules_text": "r", "prompt_text": "p", "allowed_signals": []},
    )
    exam_code = exam_resp.json()["join_code"]
    start_resp = client.post(
        "/sessions/start",
        json={"exam_code": exam_code, "participant_id": "P1", "consent_given": True, "context": {}},
    )
    session_id = start_resp.json()["session_id"]

    from app.auth import create_access_token
    from app.database import SessionLocal
    from app.models import User

    db = SessionLocal()
    other = db.query(User).filter(User.email == "otro-docente@uade.edu.ar").first()
    if not other:
        from app.auth import hash_password
        other = User(email="otro-docente@uade.edu.ar", password_hash=hash_password("1234"))
        db.add(other)
        db.commit()
        db.refresh(other)
    other_token = create_access_token(other.id)
    db.close()

    resp = client.get(f"/sessions/{session_id}", headers=auth_headers(other_token))
    assert resp.status_code == 404


def test_api_timestamps_are_explicit_utc(client, teacher_token):
    """
    Los timestamps se guardan en UTC sin zona (datetime.utcnow). Si la API los
    devuelve sin offset, el navegador los interpreta como hora local y el
    dashboard muestra horas corridas (-3 h en Argentina). Deben salir con +00:00.
    """
    from datetime import datetime

    exam = client.post(
        "/exams",
        headers=auth_headers(teacher_token),
        json={"name": "TZ", "info_text": "i", "rules_text": "r", "prompt_text": "p", "allowed_signals": []},
    ).json()
    assert exam["created_at"].endswith("+00:00")
    assert exam["current_policy"]["created_at"].endswith("+00:00")

    started = client.post(
        "/sessions/start",
        json={"exam_code": exam["join_code"], "participant_id": "P-TZ", "consent_given": True, "context": {}},
    ).json()
    client.post(f"/sessions/{started['session_id']}/end", headers={"X-Session-Token": started["session_token"]})
    detail = client.get(f"/sessions/{started['session_id']}", headers=auth_headers(teacher_token)).json()
    for field in ("started_at", "ended_at"):
        parsed = datetime.fromisoformat(detail[field])
        assert parsed.utcoffset() is not None and parsed.utcoffset().total_seconds() == 0


def test_utcnow_is_naive_utc_like_the_stored_timestamps():
    """
    B11 (revisión 13/10): `datetime.utcnow()` está deprecado desde Python 3.12. Su reemplazo
    (`models.utcnow`) tiene que devolver lo mismo que guardaba antes: hora UTC sin zona, para
    que la serialización con +00:00 (test anterior) y los datos existentes no cambien.
    """
    from datetime import datetime, timezone

    from app.models import utcnow

    now = utcnow()
    assert now.tzinfo is None
    assert abs((now - datetime.now(timezone.utc).replace(tzinfo=None)).total_seconds()) < 5
