"""Incremento 12 (R1–R2): panorama de la evaluación y relevancia de eventos según las reglas."""
import numpy as np

from app.evaluation.synthetic import SyntheticParams, generate_session
from app.processing.features import compute_all_features
from app.processing.indicators import generate_indicators
from app.processing.panorama import compute_panorama
from app.processing.pipeline import evaluate_session
from app.processing.rules import capture_signals, rules_from_stored, to_stored


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


FEATS = {
    "paste_chars_total": 900.0,
    "tab_switch_count": 9.0,
    "focus_loss_duration_total_ms": 120_000.0,
    "keydown_count": 0.0,
}


# ---- R2: reglas del examen ----

def test_rules_round_trip_in_the_signals_json_without_schema_change():
    stored = to_stored(["keyboard", "clipboard"], {"permite_pegado": True, "permite_otras_pestanas": False})
    assert stored == ["keyboard", "clipboard", "regla:permite_pegado"]
    assert capture_signals(stored) == ["keyboard", "clipboard"]
    assert rules_from_stored(stored) == {"permite_pegado": True, "permite_otras_pestanas": False}
    assert rules_from_stored(["keyboard"]) == {"permite_pegado": False, "permite_otras_pestanas": False}


def test_default_rules_leave_indicators_identical():
    base = generate_indicators(FEATS)
    for rules in (None, {}, {"permite_pegado": False, "permite_otras_pestanas": False}):
        other = generate_indicators(FEATS, rules)
        assert [(d.kind, d.level, d.description, d.explanation, d.prioritizes_review) for d in other] == \
               [(d.kind, d.level, d.description, d.explanation, d.prioritizes_review) for d in base]


def test_permitted_events_are_low_explained_and_do_not_prioritize():
    drafts = {d.kind: d for d in generate_indicators(FEATS, {"permite_pegado": True, "permite_otras_pestanas": True})}
    assert set(drafts) == {"paste_volume_alto", "cambios_pestana_frecuentes", "perdida_foco_prolongada"}
    for d in drafts.values():
        assert d.level == "low" and d.prioritizes_review is False
        assert "permitido por las reglas de esta evaluación" in d.description
        assert d.explanation["permitido_por_reglas"] is True
    assert evaluate_session(FEATS, None, {"permite_pegado": True, "permite_otras_pestanas": True}).needs_review is False
    # Solo pegado permitido: las pestañas siguen priorizando.
    only_paste = {d.kind: d for d in generate_indicators(FEATS, {"permite_pegado": True})}
    assert only_paste["paste_volume_alto"].level == "low"
    assert only_paste["perdida_foco_prolongada"].level == "high"
    assert evaluate_session(FEATS, None, {"permite_pegado": True}).needs_review is True


def test_rules_do_not_change_synthetic_sessions_without_rules():
    rng = np.random.default_rng(12)
    p = SyntheticParams()
    for prof in ("normal", "pegado_masivo", "cambio_pestana"):
        f = compute_all_features(generate_session(rng, p, prof))
        a, b = evaluate_session(f, None), evaluate_session(f, None, None)
        assert [(d.kind, d.level) for d in a.drafts] == [(d.kind, d.level) for d in b.drafts]
        assert a.needs_review == b.needs_review


def _exam(client, token, name, **extra):
    return client.post("/exams", headers=auth_headers(token), json={
        "name": name, "info_text": "i", "rules_text": "r", "prompt_text": "p",
        "allowed_signals": ["keyboard", "visibility", "clipboard"], **extra,
    }).json()


def _session(client, exam, pid, events):
    s = client.post("/sessions/start", json={
        "exam_code": exam["join_code"], "participant_id": pid, "consent_given": True, "context": {},
    }).json()
    h = {"X-Session-Token": s["session_token"]}
    client.post(f"/sessions/{s['session_id']}/events", headers=h, json={"seq": 1, "events": events})
    end = client.post(f"/sessions/{s['session_id']}/end", headers=h).json()
    return s, end


PASTE_EVENTS = [
    {"t": 0, "type": "keydown"}, {"t": 90, "type": "keyup"},
    {"t": 1_000, "type": "paste", "chars": 800},
    {"t": 60_000, "type": "keydown"}, {"t": 60_090, "type": "keyup"},
]


def test_rules_through_the_api(client, teacher_token):
    exam = _exam(client, teacher_token, "Pegado permitido", permite_pegado=True)
    pol = exam["current_policy"]
    assert pol["permite_pegado"] is True and pol["permite_otras_pestanas"] is False
    assert pol["allowed_signals"] == ["keyboard", "visibility", "clipboard"]

    info = client.get(f"/exams/{exam['join_code']}/info").json()
    assert info["allowed_signals"] == ["keyboard", "visibility", "clipboard"]

    s, end = _session(client, exam, "P-REGLA", PASTE_EVENTS)
    assert s["allowed_signals"] == ["keyboard", "visibility", "clipboard"]  # el cliente no ve la regla
    assert end["needs_review"] is False
    detail = client.get(f"/sessions/{s['session_id']}", headers=auth_headers(teacher_token)).json()
    ind = next(i for i in detail["indicators"] if i["kind"] == "paste_volume_alto")
    assert ind["level"] == "low" and ind["explanation"]["permitido_por_reglas"] is True

    # Sin la regla (default), la misma sesión prioriza como antes.
    exam2 = _exam(client, teacher_token, "Pegado no permitido")
    assert exam2["current_policy"]["permite_pegado"] is False
    _, end2 = _session(client, exam2, "P-SINREGLA", PASTE_EVENTS)
    assert end2["needs_review"] is True

    # Nueva versión de política con la regla de pestañas.
    pol2 = client.post(f"/exams/{exam2['id']}/policy", headers=auth_headers(teacher_token), json={
        "info_text": "i", "rules_text": "r", "allowed_signals": ["visibility"], "permite_otras_pestanas": True,
    }).json()
    assert pol2["permite_otras_pestanas"] is True and pol2["allowed_signals"] == ["visibility"]


# ---- R1: panorama ----

def test_compute_panorama_aggregates_existing_metrics_and_indicators():
    metrics = {
        "a": {"session_duration_ms": 1000.0, "idle_ratio": 0.1, "paste_chars_total": 0.0, "tab_switch_count": 0.0},
        "b": {"session_duration_ms": 2000.0, "idle_ratio": 0.2, "paste_chars_total": 300.0, "tab_switch_count": 2.0},
        "c": {"session_duration_ms": 3000.0, "idle_ratio": 0.3, "paste_chars_total": 0.0, "tab_switch_count": 7.0},
        "d": {"session_duration_ms": 4000.0, "idle_ratio": 0.4, "paste_chars_total": 0.0, "tab_switch_count": 1.0},
    }
    indicators = [
        {"session_id": "b", "kind": "paste_volume_alto", "explanation": {"permitido_por_reglas": True}},
        {"session_id": "c", "kind": "cambios_pestana_frecuentes", "explanation": {}},
        {"session_id": "c", "kind": "atipico_modelo_poblacional",
         "explanation": {"top_features": [{"metric": "mean_dwell_time_ms"}, {"metric": "std_dwell_time_ms"}]}},
        {"session_id": "d", "kind": "atipico_modelo_poblacional",
         "explanation": {"top_features": [{"metric": "mean_dwell_time_ms"}]}},
        {"session_id": "zz", "kind": "paste_volume_alto", "explanation": {}},  # no finalizada: se ignora
    ]
    p = compute_panorama(metrics, indicators, {"c": True, "d": True})
    assert p["n_sesiones"] == 4 and p["sesiones_requieren_revision"] == 2
    dur = next(m for m in p["metricas"] if m["metric"] == "session_duration_ms")
    assert (dur["n"], dur["mediana"], dur["p25"], dur["p75"]) == (4, 2500.0, 1750.0, 3250.0)
    focus = next(m for m in p["metricas"] if m["metric"] == "focus_loss_duration_total_ms")
    assert focus["n"] == 0 and focus["mediana"] is None
    kinds = {i["kind"]: i for i in p["indicadores"]}
    assert kinds["paste_volume_alto"]["sesiones"] == 1 and kinds["paste_volume_alto"]["permitidas_por_reglas"] == 1
    assert kinds["atipico_modelo_poblacional"]["sesiones"] == 2
    assert p["modelo"]["sesiones_marcadas"] == 2 and p["modelo"]["porcentaje"] == 0.5
    assert p["modelo"]["metricas_frecuentes"] == [
        {"metric": "mean_dwell_time_ms", "sesiones": 2}, {"metric": "std_dwell_time_ms", "sesiones": 1},
    ]


def test_panorama_endpoint(client, teacher_token):
    exam = _exam(client, teacher_token, "Panorama")
    empty = client.get(f"/exams/{exam['id']}/panorama", headers=auth_headers(teacher_token)).json()
    assert empty["n_sesiones"] == 0 and empty["indicadores"] == []

    _session(client, exam, "P-1", PASTE_EVENTS)
    _session(client, exam, "P-2", [{"t": 0, "type": "keydown"}, {"t": 80, "type": "keyup"},
                                   {"t": 500, "type": "visibility", "state": "hidden"},
                                   {"t": 2_500, "type": "visibility", "state": "visible"}])
    # Una sesión sin finalizar no cuenta.
    client.post("/sessions/start", json={"exam_code": exam["join_code"], "participant_id": "P-3",
                                         "consent_given": True, "context": {}})

    r = client.get(f"/exams/{exam['id']}/panorama", headers=auth_headers(teacher_token))
    assert r.status_code == 200
    p = r.json()
    assert p["n_sesiones"] == 2 and p["sesiones_requieren_revision"] == 1
    paste = next(m for m in p["metricas"] if m["metric"] == "paste_chars_total")
    assert (paste["n"], paste["mediana"]) == (2, 400.0)
    tabs = next(m for m in p["metricas"] if m["metric"] == "tab_switch_count")
    assert tabs["p75"] == 0.75
    assert [i["kind"] for i in p["indicadores"]] == ["paste_volume_alto"]
    assert p["modelo"]["sesiones_marcadas"] == 0  # población insuficiente: el modelo no se usó

    assert client.get(f"/exams/{exam['id']}/panorama").status_code in (401, 403)
    assert client.get("/exams/no-existe/panorama", headers=auth_headers(teacher_token)).status_code == 404
