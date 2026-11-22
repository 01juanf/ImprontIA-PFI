"""Ejercicios múltiples, enunciado en PDF y respuestas por ejercicio (rediseño, nov. 2026)."""

PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


def _crear(client, token, **extra):
    body = {
        "name": "Parcial con ejercicios",
        "prompt_text": "Ver ejercicios",
        "info_text": "Se registra teclado.",
        "rules_text": "Libro cerrado.",
        "allowed_signals": ["keyboard"],
        **extra,
    }
    r = client.post("/exams", json=body, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    return r.json()


def _iniciar(client, code):
    r = client.post("/sessions/start", json={"exam_code": code, "participant_id": "P-EJ", "consent_given": True})
    assert r.status_code == 200, r.text
    return r.json()


def test_examen_con_ejercicios_y_respuestas_por_ejercicio(client, teacher_token):
    items = [{"id": "1", "enunciado": "Definí clave primaria."}, {"id": "2", "enunciado": "Normalizá el esquema."}]
    exam = _crear(client, teacher_token, items=items)
    assert exam["items"] == items and exam["tiene_pdf"] is False

    start = _iniciar(client, exam["join_code"])
    assert start["items"] == items

    h = {"X-Session-Token": start["session_token"]}
    sid = start["session_id"]
    ev = {"seq": 1, "events": [{"t": 10, "type": "keydown", "item_ref": "2"}, {"t": 90, "type": "keyup", "dwell": 80, "item_ref": "2"}]}
    assert client.post(f"/sessions/{sid}/events", json=ev, headers=h).status_code == 201
    r = client.post(f"/sessions/{sid}/end", json={"respuestas": {"1": "Identifica la fila.", "2": "Paso a 3FN."}}, headers=h)
    assert r.status_code == 200, r.text

    d = client.get(f"/sessions/{sid}", headers={"Authorization": f"Bearer {teacher_token}"}).json()
    assert d["respuestas"] == {"1": "Identifica la fila.", "2": "Paso a 3FN."}
    assert d["items"] == items
    assert d["respuesta"].startswith("Ejercicio 1:\nIdentifica la fila.")


def test_ids_de_ejercicio_repetidos(client, teacher_token):
    r = client.post(
        "/exams",
        json={"name": "x", "prompt_text": "x", "info_text": "x", "rules_text": "x", "allowed_signals": [],
              "items": [{"id": "1"}, {"id": "1"}]},
        headers={"Authorization": f"Bearer {teacher_token}"},
    )
    assert r.status_code == 422


def test_pdf_del_enunciado(client, teacher_token):
    auth = {"Authorization": f"Bearer {teacher_token}"}
    exam = _crear(client, teacher_token, items=[{"id": "1"}, {"id": "2"}, {"id": "3"}])

    malo = client.put(f"/exams/{exam['id']}/pdf", files={"archivo": ("x.pdf", b"no es pdf", "application/pdf")}, headers=auth)
    assert malo.status_code == 422

    r = client.put(f"/exams/{exam['id']}/pdf", files={"archivo": ("parcial.pdf", PDF, "application/pdf")}, headers=auth)
    assert r.status_code == 200 and r.json()["tiene_pdf"] is True and r.json()["pdf_nombre"] == "parcial.pdf"

    docente = client.get(f"/exams/{exam['id']}/pdf", headers=auth)
    assert docente.status_code == 200 and docente.content == PDF

    # El estudiante lo ve solo con el token de su sesión (después del consentimiento).
    start = _iniciar(client, exam["join_code"])
    assert start["tiene_pdf"] is True
    sid = start["session_id"]
    assert client.get(f"/sessions/{sid}/enunciado.pdf", headers={"X-Session-Token": "otro"}).status_code == 401
    est = client.get(f"/sessions/{sid}/enunciado.pdf", headers={"X-Session-Token": start["session_token"]})
    assert est.status_code == 200 and est.content == PDF

    # Eliminar la evaluación borra también el PDF.
    assert client.delete(f"/exams/{exam['id']}", headers=auth).status_code == 204


def test_pdf_del_enunciado_respeta_el_limite_de_vercel(client, teacher_token):
    """Vercel limita a 4,5 MB cada pedido y cada respuesta: el enunciado admite hasta 4 MB."""
    from app.routers.sessions import MAX_PDF_BYTES

    assert MAX_PDF_BYTES == 4 * 1024 * 1024
    auth = {"Authorization": f"Bearer {teacher_token}"}
    exam = _crear(client, teacher_token, items=[{"id": "1"}])
    grande = PDF + b"0" * (MAX_PDF_BYTES + 1 - len(PDF))
    r = client.put(f"/exams/{exam['id']}/pdf", files={"archivo": ("g.pdf", grande, "application/pdf")}, headers=auth)
    assert r.status_code == 413
    justo = PDF + b"0" * (MAX_PDF_BYTES - len(PDF))
    r = client.put(f"/exams/{exam['id']}/pdf", files={"archivo": ("j.pdf", justo, "application/pdf")}, headers=auth)
    assert r.status_code == 200
