from app.processing.anomaly import MIN_SESSIONS_FOR_MODEL, score_against_population


def _normal_session(i: int) -> dict:
    # Cluster apretado alrededor de valores "típicos" (con pequeña variación por sesión).
    return {
        "mean_dwell_time_ms": 80.0 + (i % 3),
        "std_dwell_time_ms": 10.0 + (i % 2),
        "mean_flight_time_ms": 120.0 + (i % 4),
        "mean_mouse_speed_px_ms": 0.5,
        "std_mouse_speed_px_ms": 0.1,
    }


def test_returns_none_below_minimum_population():
    population = [_normal_session(i) for i in range(MIN_SESSIONS_FOR_MODEL - 1)]
    result = score_against_population(_normal_session(0), population)
    assert result is None


def test_flags_a_clear_outlier_against_a_tight_population():
    population = [_normal_session(i) for i in range(20)]
    outlier = {
        "mean_dwell_time_ms": 900.0,   # muy por fuera del cluster ~80ms
        "std_dwell_time_ms": 300.0,
        "mean_flight_time_ms": 4000.0,
        "mean_mouse_speed_px_ms": 50.0,
        "std_mouse_speed_px_ms": 20.0,
    }
    result = score_against_population(outlier, population)
    assert result is not None
    assert result.is_anomalous is True
    assert len(result.top_features) == 2
    # La feature más desviada debería tener un z-score grande.
    assert abs(result.top_features[0]["z_score"]) > abs(result.top_features[1]["z_score"])


def test_typical_session_within_population_is_not_flagged():
    population = [_normal_session(i) for i in range(20)]
    result = score_against_population(_normal_session(5), population)
    assert result is not None
    assert result.is_anomalous is False
