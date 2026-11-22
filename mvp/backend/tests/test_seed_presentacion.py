"""
Datos de demostración para la plataforma desplegada (scripts/seed_presentacion.py, 30/10/2026):
escala liviana, reintentos HTTP, borrado acotado a la demo y fechas con UPDATE masivos.
"""
from datetime import datetime, timezone

import httpx
import numpy as np
import pytest

from app.processing.features import compute_all_features
from app.processing.indicators import generate_indicators
from app.processing.rules import rules_from_stored, to_stored
from scripts import seed_presentacion as sp


def _plan(clave):
    return next(p for p in sp.PLAN if p.clave == clave)


def test_aligerar_conserva_pares_y_demas_eventos():
    from app.evaluation.synthetic import SyntheticParams, generate_session

    events = generate_session(np.random.default_rng(1), SyntheticParams(keys_range=(1500, 1501)), "cambio_pestana")
    liv = sp.aligerar(events, 5)
    no_teclas = [e for e in events if e["type"] not in ("keydown", "keyup")]
    assert [e for e in liv if e["type"] not in ("keydown", "keyup")] == no_teclas
    downs = [e for e in liv if e["type"] == "keydown"]
    ups = [e for e in liv if e["type"] == "keyup"]
    assert len(downs) == len(ups) == 300
    # Cada pulsación conservada mantiene su duración original (keydown seguido de su keyup).
    teclas = [e for e in liv if e["type"] in ("keydown", "keyup")]
    assert all(a["type"] == "keydown" and b["type"] == "keyup" for a, b in zip(teclas[::2], teclas[1::2]))
    f_c, f_l = compute_all_features(events), compute_all_features(liv)
    assert f_l["mean_dwell_time_ms"] == pytest.approx(f_c["mean_dwell_time_ms"], rel=0.05)
    assert f_l["session_duration_ms"] == pytest.approx(f_c["session_duration_ms"], rel=0.02)
    assert sp.aligerar(events, 1) is events


@pytest.mark.parametrize("clave", ["p2m", "tp"])
def test_escala_liviana_misma_historia(clave):
    """Mismos participantes, perfiles, respuestas e indicadores por reglas que la escala completa,
    con ~5 veces menos eventos y la misma duración de sesión."""
    plan = _plan(clave)
    reglas = rules_from_stored(to_stored(sp.TODAS_LAS_SENALES, {"permite_pegado": plan.libro_abierto,
                                                                 "permite_otras_pestanas": plan.libro_abierto}))
    completa = sp.preparar_sesiones(plan, sp.ESCALAS["completa"])
    liviana = sp.preparar_sesiones(plan, sp.ESCALAS["liviana"])
    assert [(s["participante"], s["perfil"], s["respuesta"]) for s in completa] == \
           [(s["participante"], s["perfil"], s["respuesta"]) for s in liviana]
    n_c = sum(len(s["events"]) for s in completa)
    n_l = sum(len(s["events"]) for s in liviana)
    assert n_l < n_c / 3.5
    for c, l in zip(completa, liviana):
        assert l["span_ms"] == pytest.approx(c["span_ms"], abs=2_000)
        if c["perfil"] == "normal":
            assert l["span_ms"] > 5 * 60_000  # un parcial, no una sesión de 2 minutos
        k_c = sorted((d.kind, d.level) for d in generate_indicators(compute_all_features(c["events"]), reglas))
        k_l = sorted((d.kind, d.level) for d in generate_indicators(compute_all_features(l["events"]), reglas))
        assert k_c == k_l, c["participante"]


class _FakeClient:
    def __init__(self, respuestas):
        self.respuestas = list(respuestas)
        self.llamadas = 0

    def request(self, method, url, **kw):
        self.llamadas += 1
        r = self.respuestas.pop(0)
        if isinstance(r, Exception):
            raise r
        return httpx.Response(r, json={"ok": True}, request=httpx.Request(method, "http://x" + url))


def test_api_reintenta_transitorios_en_idempotentes():
    fake = _FakeClient([503, httpx.ReadTimeout("lento"), httpx.ConnectError("caída"), 201])
    api = sp.Api(fake, espera=0, verbose=False)
    assert api.post("/sessions/x/events", what="lote").status_code == 201
    assert fake.llamadas == 4


def test_api_no_repite_a_ciegas_un_post_no_idempotente():
    api = sp.Api(_FakeClient([httpx.ReadTimeout("lento")]), espera=0, verbose=False)
    with pytest.raises(sp.Ambiguo):
        api.post("/exams", what="crear", idempotente=False)
    # Si no se pudo conectar, el pedido no salió: se reintenta aunque no sea idempotente.
    fake = _FakeClient([httpx.ConnectError("caída"), 200])
    assert sp.Api(fake, espera=0, verbose=False).post("/exams", what="crear", idempotente=False).status_code == 200


def test_api_error_definitivo_no_se_reintenta():
    fake = _FakeClient([422])
    with pytest.raises(SystemExit):
        sp.Api(fake, espera=0, verbose=False).post("/sessions/x/events", what="lote")
    assert fake.llamadas == 1


def test_borrado_solo_evaluaciones_de_la_demo_y_con_confirmacion(monkeypatch):
    assert sp.es_demo("Recuperatorio · Bases de Datos I")
    assert sp.es_demo("Recuperatorio · Bases de Datos I [DEMO]")
    assert not sp.es_demo("Parcial real · Algoritmos")
    sp.confirmar_borrado("d@x.com", None, destino_remoto=False, cuantas=6)  # SQLite local: sin preguntar
    sp.confirmar_borrado("d@x.com", "D@X.com", destino_remoto=True, cuantas=6)
    with pytest.raises(SystemExit):
        sp.confirmar_borrado("d@x.com", "otro@x.com", destino_remoto=True, cuantas=6)
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    with pytest.raises(SystemExit):
        sp.confirmar_borrado("d@x.com", None, destino_remoto=True, cuantas=6)


def test_carga_reducida_fecha_y_borra_solo_la_demo(client, monkeypatch, teacher_token):
    """De punta a punta en modo local con un plan chico: carga, fecha con UPDATE masivos,
    se niega a mezclar con evaluaciones ajenas a la demo y --solo-borrar no las toca."""
    from app.database import SessionLocal
    from app.models import Exam, Session

    chico = [
        sp.PlanEvaluacion("p1m", sp.PLAN[0].nombre, sp.PROMPT_P1, sp.RESP_P1, dias_atras=45, hora_local=9,
                          normales=3, anomalas={"pegado_masivo": 1}, semilla=11),
        sp.PlanEvaluacion("recu", sp.PLAN[-1].nombre, sp.PROMPT_RECU, sp.RESP_RECU, dias_atras=0, hora_local=-1,
                          normales=2, anomalas={}, abierta=True, revision="ninguna", semilla=16),
    ]
    monkeypatch.setattr(sp, "PLAN", chico)
    email, clave = "demo-seed@uade.edu.ar", "clave-demo"
    ancla = "2026-10-30T12:00:00-03:00"
    assert sp.main(["--email", email, "--clave", clave, "--escala", "liviana", "--ancla", ancla]) == 0

    db = SessionLocal()
    try:
        exams = {e.name: e for e in db.query(Exam).join(Exam.teacher).filter_by(email=email)}
        p1 = exams[sp.PLAN[0].nombre]
        assert p1.created_at.date() < datetime(2026, 9, 15).date()  # 45 días antes, y no "hoy"
        assert p1.cerrada_at is not None and p1.cerrada_at.date() == datetime(2026, 9, 15).date()
        sesiones = db.query(Session).filter(Session.exam_id == p1.id).all()
        assert all(s.context.get("origen") == "demo_sintetica" and s.condicion_simulacion is None for s in sesiones)
        assert all((s.ended_at - s.started_at).total_seconds() > 8 * 60 for s in sesiones)
        assert exams[sp.PLAN[-1].nombre].cerrada_at is None
    finally:
        db.close()

    # Ya cargada: sin --reiniciar no hace nada.
    assert sp.main(["--email", email, "--clave", clave, "--ancla", ancla]) == 1

    # Una evaluación que no es de la demo: no se mezcla, y --solo-borrar no la toca.
    tok = client.post("/auth/login", json={"email": email, "password": clave}).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    real = client.post("/exams", headers=h, json={
        "name": "Parcial real · Algoritmos", "prompt_text": "x", "info_text": "i", "rules_text": "r",
        "allowed_signals": ["keyboard"]}).json()
    assert sp.main(["--email", email, "--clave", clave, "--reiniciar", "--ancla", ancla]) == 1
    # Una evaluación REAL que se llama igual que una de la demo (sin sesiones sintéticas): no se borra.
    homonima = client.post("/exams", headers=h, json={
        "name": sp.PLAN[0].nombre, "prompt_text": "x", "info_text": "i", "rules_text": "r",
        "allowed_signals": ["keyboard"]}).json()
    vacia = client.post("/exams", headers=h, json={
        "name": sp.PLAN[-1].nombre, "prompt_text": "x", "info_text": "i", "rules_text": "r",
        "allowed_signals": ["keyboard"]}).json()
    r = client.post("/sessions/start", json={"exam_code": homonima["join_code"], "participant_id": "P-REAL",
                                             "consent_given": True})
    assert r.status_code == 200
    # Una sesión rendida en vivo en una evaluación de la demo no impide borrarla.
    recu = next(e for e in client.get("/exams", headers=h).json()
                if e["name"] == sp.PLAN[-1].nombre and e["id"] != vacia["id"])
    assert client.post("/sessions/start", json={"exam_code": recu["join_code"], "participant_id": "P-450",
                                                "consent_given": True}).status_code == 200
    # Con TEST_DATABASE_URL (PostgreSQL) el script la trata como remota: exige confirmación.
    assert sp.main(["--email", email, "--clave", clave, "--solo-borrar", "--si-borrar", email]) == 0
    restantes = client.get("/exams", headers=h).json()
    assert sorted(e["id"] for e in restantes) == sorted([real["id"], homonima["id"], vacia["id"]])
    # Las evaluaciones de otros docentes no se ven ni se tocan.
    otras = client.get("/exams", headers={"Authorization": f"Bearer {teacher_token}"})
    assert otras.status_code == 200


def test_fechar_rechaza_una_base_que_no_es_la_de_la_api(tmp_path):
    from sqlalchemy import create_engine

    from app.database import Base
    from app import models  # noqa: F401

    url = f"sqlite:///{tmp_path / 'otra.db'}"
    Base.metadata.create_all(create_engine(url))
    datos = {"exam": {"id": "no-existe"}, "sesiones": []}
    with pytest.raises(SystemExit, match="no es la de la API"):
        sp.fechar(url, datetime.now(timezone.utc), [(sp.PLAN[0], datos, [])])
