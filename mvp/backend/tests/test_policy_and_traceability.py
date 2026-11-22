"""
Pruebas de integración para el rediseño de esquema del Incremento 5:
política versionada (RNF04), item_ref por evento/métrica, trazabilidad
relacional indicador<->métrica (RNF05) y revisión<->indicador (RF11).
"""


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def create_exam(client, token, **overrides):
    payload = {
        "name": "Examen de prueba",
        "prompt_text": "consigna",
        "info_text": "info v1",
        "rules_text": "reglas v1",
        "allowed_signals": ["keyboard", "clipboard"],
    }
    payload.update(overrides)
    resp = client.post("/exams", headers=auth_headers(token), json=payload)
    assert resp.status_code == 200
    return resp.json()


def start_session(client, join_code, participant_id="P1"):
    resp = client.post(
        "/sessions/start",
        json={"exam_code": join_code, "participant_id": participant_id, "consent_given": True, "context": {}},
    )
    assert resp.status_code == 200
    return resp.json()


def test_policy_change_does_not_reinterpret_an_already_started_session(client, teacher_token):
    """RNF04: una sesión ya iniciada mantiene la política que aceptó, aunque el examen cambie después."""
    exam = create_exam(client, teacher_token, info_text="info original")
    started = start_session(client, exam["join_code"])

    # El docente edita la política DESPUÉS de que el estudiante ya inició sesión.
    update_resp = client.post(
        f"/exams/{exam['id']}/policy",
        headers=auth_headers(teacher_token),
        json={"info_text": "info nueva", "rules_text": "reglas nuevas", "allowed_signals": ["mouse"]},
    )
    assert update_resp.status_code == 200

    # La info pública ahora refleja la versión nueva...
    public = client.get(f"/exams/{exam['join_code']}/info").json()
    assert public["info_text"] == "info nueva"

    # ...pero la sesión ya iniciada se procesa con las señales que aceptó originalmente:
    # un evento de teclado (permitido en la política v1) debe seguir contando.
    client.post(
        f"/sessions/{started['session_id']}/events",
        headers={"X-Session-Token": started["session_token"]},
        json={"seq": 1, "events": [{"t": 0, "type": "keydown"}]},
    )
    end = client.post(f"/sessions/{started['session_id']}/end", headers={"X-Session-Token": started["session_token"]})
    assert end.status_code == 200

    detail = client.get(f"/sessions/{started['session_id']}", headers=auth_headers(teacher_token)).json()
    assert detail["event_count"] == 1


def test_item_ref_produces_per_item_metrics(client, teacher_token):
    exam = create_exam(client, teacher_token)
    started = start_session(client, exam["join_code"])

    client.post(
        f"/sessions/{started['session_id']}/events",
        headers={"X-Session-Token": started["session_token"]},
        json={
            "seq": 1,
            "events": [
                {"t": 0, "type": "paste", "chars": 50, "item_ref": "pregunta_1"},
                {"t": 100, "type": "paste", "chars": 60, "item_ref": "pregunta_2"},
            ],
        },
    )
    client.post(f"/sessions/{started['session_id']}/end", headers={"X-Session-Token": started["session_token"]})

    detail = client.get(f"/sessions/{started['session_id']}", headers=auth_headers(teacher_token)).json()
    item_metrics = {m["item_ref"] for m in detail["metrics"] if m["item_ref"]}
    assert item_metrics == {"pregunta_1", "pregunta_2"}
    global_paste = next(m for m in detail["metrics"] if m["name"] == "paste_chars_total" and m["item_ref"] is None)
    assert global_paste["value"] == 110  # el agregado global suma ambos ítems


def test_indicator_links_to_the_metric_that_originated_it(client, teacher_token):
    """RNF05: el indicador debe poder rastrearse hasta la métrica real (relación N:M), no solo el JSON."""
    exam = create_exam(client, teacher_token)
    started = start_session(client, exam["join_code"])

    client.post(
        f"/sessions/{started['session_id']}/events",
        headers={"X-Session-Token": started["session_token"]},
        json={"seq": 1, "events": [{"t": 0, "type": "paste", "chars": 999}]},
    )
    client.post(f"/sessions/{started['session_id']}/end", headers={"X-Session-Token": started["session_token"]})

    detail = client.get(f"/sessions/{started['session_id']}", headers=auth_headers(teacher_token)).json()
    indicator = next(i for i in detail["indicators"] if i["kind"] == "paste_volume_alto")
    assert indicator["level"] in ("low", "medium", "high")
    assert len(indicator["metric_ids"]) == 1

    linked_metric = next(m for m in detail["metrics"] if m["id"] == indicator["metric_ids"][0])
    assert linked_metric["name"] == "paste_chars_total"
    assert linked_metric["value"] == 999


def test_review_can_target_specific_indicators(client, teacher_token):
    exam = create_exam(client, teacher_token)
    started = start_session(client, exam["join_code"])
    client.post(
        f"/sessions/{started['session_id']}/events",
        headers={"X-Session-Token": started["session_token"]},
        json={"seq": 1, "events": [{"t": 0, "type": "paste", "chars": 999}]},
    )
    client.post(f"/sessions/{started['session_id']}/end", headers={"X-Session-Token": started["session_token"]})

    detail = client.get(f"/sessions/{started['session_id']}", headers=auth_headers(teacher_token)).json()
    indicator_id = detail["indicators"][0]["id"]

    review_resp = client.post(
        f"/sessions/{started['session_id']}/reviews",
        headers=auth_headers(teacher_token),
        json={"action": "additional_validation", "notes": "revisar con el estudiante", "indicator_ids": [indicator_id]},
    )
    assert review_resp.status_code == 200
    assert review_resp.json()["indicator_ids"] == [indicator_id]

    # Un indicator_id que no pertenece a la sesión debe rechazarse.
    bad_resp = client.post(
        f"/sessions/{started['session_id']}/reviews",
        headers=auth_headers(teacher_token),
        json={"action": "marked_reviewed", "indicator_ids": ["no-existe"]},
    )
    assert bad_resp.status_code == 400


def test_population_model_flags_an_outlier_session(client, teacher_token):
    """
    Cap. 15: el indicador de IA solo aparece con población suficiente
    (MIN_SESSIONS_FOR_MODEL) y compara contra la distribución agregada,
    no contra el historial del propio estudiante.

    Nota sobre el diseño de este test: con muy poca población (<~20), la
    altura de árbol que usa Isolation Forest por defecto (ceil(log2(n)))
    queda tan chica que ni siquiera un outlier extremo en las 5 dimensiones
    se aísla — se verificó empíricamente al construir anomaly.py (ver
    comentario junto a MIN_SESSIONS_FOR_MODEL). Por eso acá se generan
    MIN_SESSIONS_FOR_MODEL + 1 sesiones "normales" con variación real
    (teclado + mouse), no solo un puñado de valores fijos.
    """
    from app.processing.anomaly import MIN_SESSIONS_FOR_MODEL

    exam = create_exam(client, teacher_token, allowed_signals=["keyboard", "mouse"])

    def run_session(dwell_ms: int, gap_ms: int, mouse_speed: float, seed: int, count: int = 40) -> str:
        started = start_session(client, exam["join_code"])
        events = []
        t = 0
        for k in range(count):
            d = dwell_ms + ((seed + k) % 11)
            g = gap_ms + ((seed + k * 3) % 17)
            events.append({"t": t, "type": "keydown"})
            events.append({"t": t + d, "type": "keyup"})
            events.append({"t": t + d + 10, "type": "mousemove", "x": k * mouse_speed, "y": 0})
            events.append({"t": t + d + 110, "type": "mousemove", "x": k * mouse_speed + mouse_speed * 10, "y": 0})
            t += d + g
        client.post(
            f"/sessions/{started['session_id']}/events",
            headers={"X-Session-Token": started["session_token"]},
            json={"seq": 1, "events": events},
        )
        client.post(f"/sessions/{started['session_id']}/end", headers={"X-Session-Token": started["session_token"]})
        return started["session_id"]

    # Población "normal": dwell/gap/mouse con variación real de sesión a sesión.
    for i in range(MIN_SESSIONS_FOR_MODEL + 1):
        run_session(dwell_ms=80, gap_ms=150, mouse_speed=0.5, seed=i)

    # Sesión muy distinta al resto en las tres dimensiones a la vez — debería marcarse como atípica.
    outlier_id = run_session(dwell_ms=300, gap_ms=500, mouse_speed=3.0, seed=99)

    # Incremento 16: el modelo no corre al finalizar cada sesión, sino al cerrar la evaluación.
    detail = client.get(f"/sessions/{outlier_id}", headers=auth_headers(teacher_token)).json()
    assert detail["estado_modelo"] == "pendiente"
    assert not any(i["kind"] == "atipico_modelo_poblacional" for i in detail["indicators"])

    closed = client.post(f"/exams/{exam['id']}/cerrar", headers=auth_headers(teacher_token))
    assert closed.status_code == 200 and closed.json()["cerrada_at"]
    detail = client.get(f"/sessions/{outlier_id}", headers=auth_headers(teacher_token)).json()
    assert detail["estado_modelo"] == "con_marca"
    assert any(i["kind"] == "atipico_modelo_poblacional" for i in detail["indicators"])


def test_policy_version_counter_and_exam_reflects_new_current_policy(client, teacher_token):
    """T11: el dashboard muestra la versión vigente; versionar no modifica la anterior."""
    exam = create_exam(client, teacher_token, info_text="v1", allowed_signals=["keyboard"])
    assert exam["policy_version"] == 1
    first_policy_id = exam["current_policy"]["id"]

    resp = client.post(
        f"/exams/{exam['id']}/policy",
        headers=auth_headers(teacher_token),
        json={"info_text": "v2", "rules_text": "reglas v2", "allowed_signals": ["keyboard", "mouse"]},
    )
    assert resp.status_code == 200
    assert resp.json()["id"] != first_policy_id

    updated = client.get(f"/exams/{exam['id']}", headers=auth_headers(teacher_token)).json()
    assert updated["policy_version"] == 2
    assert updated["current_policy"]["info_text"] == "v2"
    assert updated["current_policy"]["allowed_signals"] == ["keyboard", "mouse"]


def test_policy_update_requires_ownership(client, teacher_token):
    from app.auth import create_access_token, hash_password
    from app.database import SessionLocal
    from app.models import User

    exam = create_exam(client, teacher_token)
    db = SessionLocal()
    other = db.query(User).filter(User.email == "otro-docente-3@uade.edu.ar").first()
    if not other:
        other = User(email="otro-docente-3@uade.edu.ar", password_hash=hash_password("1234"))
        db.add(other)
        db.commit()
        db.refresh(other)
    token = create_access_token(other.id)
    db.close()

    resp = client.post(
        f"/exams/{exam['id']}/policy",
        headers=auth_headers(token),
        json={"info_text": "x", "rules_text": "x", "allowed_signals": []},
    )
    assert resp.status_code == 404
