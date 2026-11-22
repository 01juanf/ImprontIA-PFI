"""
Tests del Incremento 6: generador sintético, métricas de evaluación y
equivalencia entre el pipeline que usa la API y el que usa scripts/evaluar.py.
"""
import math

import numpy as np
import pytest

from app.evaluation.experiment import ExperimentConfig, run_experiment
from app.evaluation.metrics import eer, far_frr, score_metrics, summarize
from app.evaluation.synthetic import PROFILES_ANOMALOS, SyntheticParams, generate_session
from app.processing.anomaly import fit_population_model, score_against_population, score_with_model
from app.processing.features import compute_all_features
from app.processing.indicators import THRESHOLDS

# ---- Métricas ----


def test_far_frr_follow_the_documented_convention():
    # 4 anómalas (1) y 4 normales (0). Se escapa 1 anómala (FAR = 1/4) y hay 2 falsas alarmas (FRR = 2/4).
    y_true = [1, 1, 1, 1, 0, 0, 0, 0]
    y_pred = [1, 1, 1, 0, 1, 1, 0, 0]
    m = far_frr(y_true, y_pred)
    assert m["far"] == pytest.approx(0.25)  # anomalías no detectadas
    assert m["frr"] == pytest.approx(0.5)  # falsas alarmas
    assert (m["tp"], m["fn"], m["fp"], m["tn"]) == (3, 1, 2, 2)


def test_eer_is_zero_for_perfect_separation_and_auc_is_one():
    y = [0, 0, 0, 1, 1, 1]
    s = [0.1, 0.2, 0.3, 0.7, 0.8, 0.9]
    m = score_metrics(y, s)
    assert m["auc_roc"] == pytest.approx(1.0)
    assert m["average_precision"] == pytest.approx(1.0)
    assert m["eer"] == pytest.approx(0.0, abs=1e-9)


def test_eer_is_one_for_fully_inverted_scores():
    y = [0, 0, 0, 1, 1, 1]
    s = [0.9, 0.8, 0.7, 0.3, 0.2, 0.1]
    e, _ = eer(y, s)
    assert e == pytest.approx(1.0)


def test_eer_near_half_when_scores_carry_no_information():
    rng = np.random.default_rng(0)
    y = np.array([0] * 2000 + [1] * 2000)
    s = rng.normal(size=4000)
    e, _ = eer(y, s)
    assert abs(e - 0.5) < 0.05
    assert abs(score_metrics(y, s)["auc_roc"] - 0.5) < 0.05


def test_eer_matches_hand_computed_crossing():
    # Umbral entre 0.4 y 0.6: FRR = 1/4 (la normal 0.6), FAR = 1/4 (la anómala 0.4) -> EER = 0.25.
    y = [0, 0, 0, 0, 1, 1, 1, 1]
    s = [0.1, 0.2, 0.3, 0.6, 0.4, 0.7, 0.8, 0.9]
    e, _ = eer(y, s)
    assert e == pytest.approx(0.25)


def test_score_metrics_returns_nan_with_a_single_class():
    m = score_metrics([0, 0, 0], [0.1, 0.2, 0.3])
    assert math.isnan(m["auc_roc"]) and math.isnan(m["eer"])


def test_summarize_ignores_nan():
    s = summarize([0.1, float("nan"), 0.3])
    assert s["n"] == 2
    assert s["mean"] == pytest.approx(0.2)


# ---- Generador sintético ----


def test_generator_is_reproducible_with_the_same_seed():
    p = SyntheticParams()
    a = generate_session(np.random.default_rng(42), p, "normal")
    b = generate_session(np.random.default_rng(42), p, "normal")
    assert a == b
    c = generate_session(np.random.default_rng(43), p, "normal")
    assert a != c


def test_generated_events_use_the_capture_format_and_never_carry_text():
    """Mismo formato que capture.ts y misma garantía de privacidad (RNF01): nunca contenido."""
    events = generate_session(np.random.default_rng(1), SyntheticParams(), "pegado_masivo")
    # Sin `code`: la captura no identifica qué tecla se pulsa desde el Incremento 9 (M5, 14/10).
    allowed_keys = {"t", "type", "x", "y", "state", "chars"}
    for e in events:
        assert isinstance(e["t"], float)
        assert set(e) <= allowed_keys
        if e["type"] in ("keydown", "keyup"):
            assert set(e) == {"t", "type"}
    assert [e["t"] for e in events] == sorted(e["t"] for e in events)


def test_unknown_profile_is_rejected():
    with pytest.raises(ValueError):
        generate_session(np.random.default_rng(0), SyntheticParams(), "inventado")


def _features(profile: str, seed: int = 7, **kw) -> dict:
    return compute_all_features(generate_session(np.random.default_rng(seed), SyntheticParams(**kw), profile))


def test_rule_profiles_cross_the_thresholds_they_were_designed_for():
    for seed in range(5):
        assert _features("pegado_masivo", seed)["paste_chars_total"] > THRESHOLDS["paste_chars_total"]
        f = _features("cambio_pestana", seed)
        assert (
            f["tab_switch_count"] > THRESHOLDS["tab_switch_count"]
            or f["focus_loss_duration_total_ms"] > THRESHOLDS["focus_loss_duration_total_ms"]
        )
        assert _features("tecleo_automatizado", seed)["std_dwell_time_ms"] < THRESHOLDS["std_dwell_time_ms_low"]


def test_normal_sessions_mostly_stay_below_rule_thresholds():
    rng = np.random.default_rng(123)
    p = SyntheticParams()
    flagged = 0
    for _ in range(50):
        f = compute_all_features(generate_session(rng, p, "normal"))
        if (
            f["paste_chars_total"] > THRESHOLDS["paste_chars_total"]
            or f["tab_switch_count"] > THRESHOLDS["tab_switch_count"]
            or f["focus_loss_duration_total_ms"] > THRESHOLDS["focus_loss_duration_total_ms"]
            or (f["keydown_count"] >= 30 and f["std_dwell_time_ms"] < THRESHOLDS["std_dwell_time_ms_low"])
        ):
            flagged += 1
    assert flagged <= 2


def test_ritmo_distinto_shift_grows_with_difficulty():
    base = np.mean([_features("ritmo_distinto", s, dificultad=0.0)["mean_dwell_time_ms"] for s in range(20)])
    far = np.mean([_features("ritmo_distinto", s, dificultad=3.0)["mean_dwell_time_ms"] for s in range(20)])
    normal = np.mean([_features("normal", s)["mean_dwell_time_ms"] for s in range(20)])
    assert base == pytest.approx(normal, rel=1e-9)  # dificultad 0 = misma distribución (mismas semillas)
    assert far - normal == pytest.approx(3.0 * SyntheticParams().dwell_sd_between, rel=0.15)


# ---- Equivalencia con el pipeline real ----


def test_fit_once_score_many_equals_score_against_population():
    """El atajo que usa evaluar.py (entrenar una vez) da lo mismo que el camino de la API."""
    rng = np.random.default_rng(5)
    p = SyntheticParams()
    population = [compute_all_features(generate_session(rng, p, "normal")) for _ in range(25)]
    targets = [compute_all_features(generate_session(rng, p, prof)) for prof in ["normal", "ritmo_distinto", "tecleo_automatizado"]]
    model = fit_population_model(population)
    for t in targets:
        a = score_with_model(model, t)
        b = score_against_population(t, population)
        assert a.anomaly_score == pytest.approx(b.anomaly_score)
        assert a.is_anomalous == b.is_anomalous
        assert a.top_features == b.top_features


def test_small_experiment_runs_end_to_end_and_is_deterministic():
    cfg = ExperimentConfig(repeticiones=2, n_poblacion=25, n_normales_test=8, n_anomalas_test=8)
    r1 = run_experiment(cfg)
    r2 = run_experiment(cfg)
    assert r1["agregado"] == r2["agregado"]
    assert len(r1["registros"]) == 2 * 16
    assert set(r1["agregado"]["por_perfil"]) == set(PROFILES_ANOMALOS)
    far = r1["agregado"]["pipeline"]["far"]["mean"]
    frr = r1["agregado"]["pipeline"]["frr"]["mean"]
    assert 0.0 <= far <= 1.0 and 0.0 <= frr <= 1.0
    # Sin eventos crudos en los registros (solo lo necesario para las métricas).
    assert "events" not in r1["registros"][0]


def test_protocolo_cierre_uses_the_cohort_analysis_of_the_mvp():
    """`--protocolo cierre`: un único modelo sobre población + prueba (processing/cohort.py)."""
    from dataclasses import replace

    from app.evaluation import experiment as ex
    from app.processing.anomaly import CONTINUOUS_METRICS
    from app.processing.cohort import analizar_cohorte

    cfg = ExperimentConfig(repeticiones=1, n_poblacion=25, n_normales_test=8, n_anomalas_test=8, protocolo="cierre")
    recs = ex.run_repetition(cfg, 0)
    assert len(recs) == 16 and all(not math.isnan(r["score_modelo"]) for r in recs)

    # Mismo resultado que llamar a analizar_cohorte a mano con las mismas sesiones.
    rng = np.random.default_rng(cfg.semilla_base)
    pop = [compute_all_features(generate_session(rng, cfg.params, "normal")) for _ in range(25)]
    perfiles = ["normal"] * 8 + ex._profiles_for(8, cfg.perfiles, rng)
    test = [compute_all_features(generate_session(rng, cfg.params, p)) for p in perfiles]
    cont = lambda f: {k: f[k] for k in CONTINUOUS_METRICS if k in f}  # noqa: E731
    cohorte = {f"p{i:04d}": cont(f) for i, f in enumerate(pop)}
    cohorte.update({f"t{i:04d}": cont(f) for i, f in enumerate(test)})
    res = analizar_cohorte(cohorte)
    assert [r["perfil"] for r in recs] == perfiles
    assert [round(r["score_modelo"], 9) for r in recs] == [round(-res[f"t{i:04d}"].anomaly_score, 9) for i in range(16)]

    # El protocolo por defecto no cambió (población previa, prueba fuera de muestra).
    assert ExperimentConfig().protocolo == "poblacion_previa"
    with pytest.raises(ValueError):
        ex.run_repetition(replace(cfg, protocolo="otro"), 0)
