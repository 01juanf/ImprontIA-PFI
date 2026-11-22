from app.processing.features import (
    compute_attention_features,
    compute_clipboard_features,
    compute_idle_ratio,
    compute_keystroke_features,
    compute_mouse_features,
)


def test_keystroke_dwell_and_flight_times():
    events = [
        {"t": 0, "type": "keydown", "code": "KeyA"},
        {"t": 80, "type": "keyup", "code": "KeyA"},
        {"t": 120, "type": "keydown", "code": "KeyB"},
        {"t": 190, "type": "keyup", "code": "KeyB"},
    ]
    f = compute_keystroke_features(events)
    assert f["keydown_count"] == 2
    assert f["mean_dwell_time_ms"] == 75.0  # (80 + 70) / 2
    assert f["mean_flight_time_ms"] == 40.0  # 120 - 80


def test_mouse_speed_between_consecutive_moves():
    events = [
        {"t": 0, "type": "mousemove", "x": 0, "y": 0},
        {"t": 100, "type": "mousemove", "x": 100, "y": 0},
    ]
    f = compute_mouse_features(events)
    assert f["mean_mouse_speed_px_ms"] == 1.0  # 100px / 100ms


def test_tab_switch_and_focus_loss():
    events = [
        {"t": 1000, "type": "visibility", "state": "hidden"},
        {"t": 6000, "type": "visibility", "state": "visible"},
    ]
    f = compute_attention_features(events)
    assert f["tab_switch_count"] == 1
    assert f["focus_loss_duration_total_ms"] == 5000


def test_clipboard_counts_chars_not_content():
    events = [{"t": 0, "type": "paste", "chars": 42}]
    f = compute_clipboard_features(events)
    assert f["paste_event_count"] == 1
    assert f["paste_chars_total"] == 42
    assert "text" not in f  # nunca se guarda contenido, solo longitud


def test_idle_ratio_detects_large_gaps():
    events = [
        {"t": 0, "type": "click"},
        {"t": 5000, "type": "click"},  # gap de 5s > umbral de 2s -> idle
    ]
    f = compute_idle_ratio(events, gap_threshold_ms=2000)
    assert f["idle_ratio"] == 1.0


def test_idle_ratio_empty_or_single_event_is_zero():
    assert compute_idle_ratio([])["idle_ratio"] == 0.0
    assert compute_idle_ratio([{"t": 0, "type": "click"}])["idle_ratio"] == 0.0


def test_keystroke_pairing_without_key_code_matches_per_key_pairing():
    """
    Incremento 9: la captura ya no envía `code` (RNF01). Sin `code`, keydown/keyup se
    emparejan en orden de llegada; con teclas soltadas en orden (incluso solapadas,
    como al escribir rápido) el resultado es idéntico al emparejamiento por tecla.
    """
    with_code = [
        {"t": 0, "type": "keydown", "code": "KeyA"},
        {"t": 60, "type": "keydown", "code": "KeyB"},   # B se presiona antes de soltar A
        {"t": 90, "type": "keyup", "code": "KeyA"},
        {"t": 150, "type": "keyup", "code": "KeyB"},
        {"t": 300, "type": "keydown", "code": "KeyC"},
        {"t": 380, "type": "keyup", "code": "KeyC"},
    ]
    without_code = [{k: v for k, v in e.items() if k != "code"} for e in with_code]
    assert compute_keystroke_features(without_code) == compute_keystroke_features(with_code)
    f = compute_keystroke_features(without_code)
    assert f["mean_dwell_time_ms"] == (90 + 90 + 80) / 3


def test_synthetic_generator_reproduces_the_published_features_without_key_code():
    """
    Hallazgo M5 (revisión 13/10): el generador sintético ya no emite `code`, igual que la
    captura real desde el Incremento 9. Los valores de referencia se obtuvieron con el
    generador ANTERIOR (que sí emitía `code`) y la misma semilla: deben coincidir
    exactamente, porque se conservó el sorteo de la tecla y el generador no solapa teclas.
    Así los resultados publicados del Incremento 6 siguen siendo reproducibles.
    """
    import numpy as np

    from app.evaluation.synthetic import SyntheticParams, generate_session
    from app.processing.features import compute_all_features

    referencia = {  # perfil: (eventos, dwell medio, desvío dwell, flight medio, velocidad mouse)
        "normal": (765, 125.98828828828823, 17.376080719026454, 174.55933734939765, 0.5342915480713174),
        "tecleo_automatizado": (765, 125.6894894894896, 0.892432672931382, 174.5210843373493, 0.5343005851616499),
        "ritmo_distinto": (765, 155.98648648648626, 17.373241409842603, 244.4310240963858, 0.8355841017597567),
    }
    for profile, (n, dwell, dwell_sd, flight, mouse) in referencia.items():
        events = generate_session(np.random.default_rng(3), SyntheticParams(), profile)
        assert not any("code" in e for e in events)
        f = compute_all_features(events)
        assert (len(events), f["mean_dwell_time_ms"], f["std_dwell_time_ms"], f["mean_flight_time_ms"],
                f["mean_mouse_speed_px_ms"]) == (n, dwell, dwell_sd, flight, mouse)
