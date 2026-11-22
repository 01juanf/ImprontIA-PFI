from app.processing.indicators import THRESHOLDS, generate_indicators


def test_no_indicators_when_below_all_thresholds():
    features = {
        "paste_chars_total": 0,
        "tab_switch_count": 0,
        "focus_loss_duration_total_ms": 0,
        "keydown_count": 0,
        "std_dwell_time_ms": 999,
    }
    assert generate_indicators(features) == []


def test_paste_volume_indicator_includes_traceable_explanation():
    features = {"paste_chars_total": THRESHOLDS["paste_chars_total"] + 1}
    drafts = generate_indicators(features)
    assert len(drafts) == 1
    assert drafts[0].kind == "paste_volume_alto"
    # RF09/RNF05: el indicador debe poder rastrearse a la métrica que lo originó.
    assert drafts[0].explanation["metric"] == "paste_chars_total"
    assert drafts[0].explanation["threshold"] == THRESHOLDS["paste_chars_total"]


def test_typing_rhythm_indicator_requires_minimum_sample_size():
    # Std bajo pero con pocas teclas: no debe dispararse (muestra insuficiente).
    features = {"keydown_count": 5, "std_dwell_time_ms": 1.0}
    assert generate_indicators(features) == []

    features["keydown_count"] = 40
    drafts = generate_indicators(features)
    assert any(d.kind == "ritmo_tecleo_atipico" for d in drafts)


def test_multiple_indicators_can_fire_together():
    features = {
        "paste_chars_total": 300,
        "tab_switch_count": 10,
        "focus_loss_duration_total_ms": 0,
        "keydown_count": 0,
        "std_dwell_time_ms": 999,
    }
    kinds = {d.kind for d in generate_indicators(features)}
    assert kinds == {"paste_volume_alto", "cambios_pestana_frecuentes"}
