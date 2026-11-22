"""
Incremento 10: cierre de desvíos respecto de la especificación (cap. 15).

- Nivel del indicador del modelo poblacional por PERCENTILES sobre la línea base,
  no por un corte absoluto del score.
- Integridad de la captura: el agotamiento del buffer local y las fallas
  persistentes de sincronización llegan como eventos propios y se muestran al
  docente como indicador informativo, que no prioriza la sesión por sí solo.
"""
import pytest

from app.processing.anomaly import AnomalyResult, percentile_rank, score_against_population
from app.processing.features import compute_all_features, compute_capture_integrity, compute_idle_ratio
from app.processing.indicators import (
    PERCENTILE_HIGH,
    generate_indicators,
    indicator_from_anomaly,
    level_from_percentile,
)
from app.processing.pipeline import evaluate_session


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---- Percentiles ----


def test_percentile_rank_is_the_share_of_the_baseline_at_least_as_atypical():
    ref = [-0.2, -0.1, 0.0, 0.1, 0.2]
    assert percentile_rank(-0.3, ref) == 0.0  # más atípica que toda la línea base
    assert percentile_rank(-0.1, ref) == pytest.approx(0.4)
    assert percentile_rank(0.5, ref) == 1.0


def _normal_session(i: int) -> dict:
    return {
        "mean_dwell_time_ms": 80.0 + (i % 3),
        "std_dwell_time_ms": 10.0 + (i % 2),
        "mean_flight_time_ms": 120.0 + (i % 4),
        "mean_mouse_speed_px_ms": 0.5,
        "std_mouse_speed_px_ms": 0.1,
    }


def test_anomaly_result_reports_position_relative_to_the_population():
    population = [_normal_session(i) for i in range(20)]
    outlier = {
        "mean_dwell_time_ms": 900.0, "std_dwell_time_ms": 300.0, "mean_flight_time_ms": 4000.0,
        "mean_mouse_speed_px_ms": 50.0, "std_mouse_speed_px_ms": 20.0,
    }
    result = score_against_population(outlier, population)
    assert result.is_anomalous
    # Con una población chica el bosque tiene poca profundidad y un atípico extremo empata
    # con la sesión más atípica de la propia población (ver MIN_SESSIONS_FOR_MODEL): el
    # percentil usa "<=", así que el empate cuenta en contra y el resultado es conservador.
    assert result.population_percentile <= PERCENTILE_HIGH
    assert level_from_percentile(result.population_percentile) == "high"
    assert result.population_size == 20

    typical = score_against_population(_normal_session(5), population)
    assert not typical.is_anomalous
    assert typical.population_percentile > 0.1


def test_level_follows_the_percentile_band_not_an_absolute_score():
    assert level_from_percentile(0.0) == "high"
    assert level_from_percentile(PERCENTILE_HIGH) == "high"
    assert level_from_percentile(0.08) == "medium"
    assert level_from_percentile(None) == "medium"

    # Mismo score absoluto, distinto nivel según la posición en la línea base.
    hi = indicator_from_anomaly(AnomalyResult(True, -0.02, [], population_percentile=0.03, population_size=30))
    mid = indicator_from_anomaly(AnomalyResult(True, -0.02, [], population_percentile=0.09, population_size=30))
    assert (hi.level, mid.level) == ("high", "medium")
    assert hi.explanation["population_percentile"] == 0.03
    assert hi.explanation["population_size"] == 30
    assert hi.prioritizes_review is True


# ---- Integridad de la captura ----


def test_capture_status_events_become_integrity_metrics_and_do_not_count_as_activity():
    events = [
        {"t": 0, "type": "keydown"},
        {"t": 100, "type": "keyup"},
        {"t": 50, "type": "sync_failure", "failed_attempts": 4, "duration_ms": 90_000},
        {"t": 60, "type": "buffer_overflow", "dropped": 120, "from_t": 60, "to_t": 80_000},
        {"t": 90_000, "type": "buffer_overflow", "dropped": 30, "from_t": 85_000, "to_t": 90_000},
    ]
    f = compute_capture_integrity(events)
    assert f == {"capture_dropped_events": 150.0, "sync_failure_count": 1.0}
    # La duración de la sesión y la inactividad solo miran interacciones del estudiante.
    assert compute_idle_ratio(events)["session_duration_ms"] == 100


def test_incomplete_capture_is_informative_and_does_not_prioritize_review():
    features = compute_all_features([
        {"t": 0, "type": "keydown"}, {"t": 80, "type": "keyup"},
        {"t": 10, "type": "buffer_overflow", "dropped": 40},
    ])
    drafts = generate_indicators(features)
    assert [d.kind for d in drafts] == ["captura_incompleta"]
    assert drafts[0].level == "low" and drafts[0].prioritizes_review is False
    assert drafts[0].metric_names == ["capture_dropped_events"]
    assert evaluate_session(features, None).needs_review is False

    # Si además hay un indicador que prioriza, la sesión sí queda marcada.
    features["paste_chars_total"] = 999
    assert evaluate_session(features, None).needs_review is True


def test_incomplete_capture_end_to_end_through_the_api(client, teacher_token):
    exam = client.post("/exams", headers=auth_headers(teacher_token), json={
        "name": "Captura incompleta", "info_text": "i", "rules_text": "r", "prompt_text": "p",
        "allowed_signals": ["keyboard"],
    }).json()
    s = client.post("/sessions/start", json={
        "exam_code": exam["join_code"], "participant_id": "P-RED", "consent_given": True, "context": {},
    }).json()
    h = {"X-Session-Token": s["session_token"]}
    client.post(f"/sessions/{s['session_id']}/events", headers=h, json={"seq": 1, "events": [
        {"t": 0, "type": "keydown"}, {"t": 90, "type": "keyup"},
        {"t": 5_000, "type": "sync_failure", "failed_attempts": 3, "duration_ms": 35_000},
    ]})
    end = client.post(f"/sessions/{s['session_id']}/end", headers=h).json()
    assert end["needs_review"] is False

    detail = client.get(f"/sessions/{s['session_id']}", headers=auth_headers(teacher_token)).json()
    ind = next(i for i in detail["indicators"] if i["kind"] == "captura_incompleta")
    assert ind["level"] == "low"
    linked = next(m for m in detail["metrics"] if m["id"] in ind["metric_ids"])
    assert (linked["name"], linked["value"]) == ("sync_failure_count", 1.0)
