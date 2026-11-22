"""
Protocolo de evaluación reproducible del pipeline (Incremento 6).

Por cada repetición r (semilla = semilla_base + r):
1. Se genera una POBLACIÓN de sesiones normales de una misma evaluación
   (`n_poblacion`, opcionalmente con una fracción `contaminacion_poblacion`
   de anómalas, porque en un examen real la población tampoco está limpia).
   Es la línea base poblacional contra la que se compara (cap. 15).
2. Se entrena el Isolation Forest UNA vez sobre esa población
   (anomaly.fit_population_model), igual que haría el backend con las
   sesiones ya finalizadas del examen.
3. Se genera un conjunto de PRUEBA disjunto: `n_normales_test` normales y
   `n_anomalas_test` anómalas repartidas en partes iguales entre los perfiles.
4. Cada sesión de prueba pasa por el pipeline real: eventos ->
   features.compute_all_features -> pipeline.evaluate_session (reglas +
   modelo). Se registra si quedó marcada para revisión, qué indicadores se
   dispararon y el score continuo del modelo.

Protocolo `cierre` (paquete de reproducibilidad, entrega final): replica el análisis al
cierre de la evaluación del Incremento 16 (processing/cohort.py, routers/exams.py). En lugar
de entrenar con una población previa y puntuar la prueba fuera de muestra, la COHORTE es la
población más las sesiones de prueba; analizar_cohorte entrena un único modelo con todas
(con las métricas continuas que lee routers/exams.py) y cada sesión de prueba se puntúa
contra ese modelo (transductivo). Las reglas se calculan igual, por sesión. La prevalencia
de anómalas en la cohorte es n_anomalas / (n_poblacion + n_normales + n_anomalas).

Los hiperparámetros del pipeline (umbrales de reglas, `contamination=0.1`)
NO se ajustan mirando las etiquetas de prueba (Goldstein & Uchida 2016): se
evalúan tal como están en el código del MVP.
"""
from dataclasses import asdict, dataclass, field

import numpy as np

from ..processing.anomaly import CONTINUOUS_METRICS, fit_population_model
from ..processing.cohort import analizar_cohorte
from ..processing.indicators import generate_indicators, indicator_from_anomaly
from ..processing.features import compute_all_features
from ..processing.pipeline import PipelineOutcome, evaluate_session
from .metrics import far_frr, score_metrics, summarize
from .synthetic import PROFILES_ANOMALOS, SyntheticParams, generate_session

PROTOCOLOS = ("poblacion_previa", "cierre")
RULE_KINDS = ["paste_volume_alto", "cambios_pestana_frecuentes", "perdida_foco_prolongada", "ritmo_tecleo_atipico"]
MODEL_KIND = "atipico_modelo_poblacional"


@dataclass
class ExperimentConfig:
    repeticiones: int = 20
    semilla_base: int = 2026
    n_poblacion: int = 40
    contaminacion_poblacion: float = 0.0
    n_normales_test: int = 40
    n_anomalas_test: int = 40
    perfiles: list = field(default_factory=lambda: list(PROFILES_ANOMALOS))
    params: SyntheticParams = field(default_factory=SyntheticParams)
    # "poblacion_previa": protocolo del Incremento 6 (modelo entrenado con una población previa,
    # prueba fuera de muestra). "cierre": análisis de la cohorte al cierre (Incremento 16).
    protocolo: str = "poblacion_previa"

    def as_dict(self) -> dict:
        d = asdict(self)
        d["params"] = self.params.as_dict()
        return d


def _profiles_for(n: int, perfiles: list, rng: np.random.Generator) -> list[str]:
    out = [perfiles[i % len(perfiles)] for i in range(n)]
    rng.shuffle(out)
    return out


def run_repetition(cfg: ExperimentConfig, rep: int) -> list[dict]:
    """Devuelve un registro por sesión de prueba (sin eventos crudos)."""
    rng = np.random.default_rng(cfg.semilla_base + rep)

    n_contam = int(round(cfg.n_poblacion * cfg.contaminacion_poblacion))
    pop_profiles = ["normal"] * (cfg.n_poblacion - n_contam) + _profiles_for(n_contam, cfg.perfiles, rng)
    population = [compute_all_features(generate_session(rng, cfg.params, p)) for p in pop_profiles]
    if cfg.protocolo not in PROTOCOLOS:
        raise ValueError(f"protocolo desconocido: {cfg.protocolo}")

    test_profiles = ["normal"] * cfg.n_normales_test + _profiles_for(cfg.n_anomalas_test, cfg.perfiles, rng)
    test_features = [compute_all_features(generate_session(rng, cfg.params, p)) for p in test_profiles]

    if cfg.protocolo == "cierre":
        def continuas(f: dict) -> dict:
            return {k: f[k] for k in CONTINUOUS_METRICS if k in f}  # lo que lee routers/exams.py

        cohorte = {f"p{i:04d}": continuas(f) for i, f in enumerate(population)}
        cohorte.update({f"t{i:04d}": continuas(f) for i, f in enumerate(test_features)})
        resultados = analizar_cohorte(cohorte)
        outcomes = []
        for i, f in enumerate(test_features):
            anomaly = resultados[f"t{i:04d}"]
            drafts = generate_indicators(f)
            d = indicator_from_anomaly(anomaly)
            if d:
                drafts.append(d)
            outcomes.append(PipelineOutcome(drafts=drafts, anomaly=anomaly))
    else:
        pop_model = fit_population_model(population)
        outcomes = [evaluate_session(f, pop_model) for f in test_features]

    records = []
    for i, (profile, outcome) in enumerate(zip(test_profiles, outcomes)):
        kinds = [d.kind for d in outcome.drafts]
        records.append({
            "rep": rep,
            "idx": i,
            "perfil": profile,
            "y_true": 0 if profile == "normal" else 1,
            "marcada": int(outcome.needs_review),
            "marcada_reglas": int(any(k in RULE_KINDS for k in kinds)),
            "marcada_modelo": int(MODEL_KIND in kinds),
            # -decision_function: más alto = más atípico (NaN si no hubo modelo)
            "score_modelo": -outcome.anomaly.anomaly_score if outcome.anomaly else float("nan"),
            "indicadores": kinds,
        })
    return records


def _metrics_for(records: list[dict]) -> dict:
    y = [r["y_true"] for r in records]
    out = {
        "pipeline": far_frr(y, [r["marcada"] for r in records]),
        "solo_reglas": far_frr(y, [r["marcada_reglas"] for r in records]),
        "solo_modelo": far_frr(y, [r["marcada_modelo"] for r in records]),
        "modelo_score": score_metrics(y, [r["score_modelo"] for r in records]),
    }
    normals = [r for r in records if r["y_true"] == 0]
    out["por_perfil"] = {}
    for perfil in sorted({r["perfil"] for r in records if r["y_true"] == 1}):
        anom = [r for r in records if r["perfil"] == perfil]
        sub = normals + anom
        out["por_perfil"][perfil] = {
            "deteccion_pipeline": float(np.mean([r["marcada"] for r in anom])),
            "deteccion_reglas": float(np.mean([r["marcada_reglas"] for r in anom])),
            "deteccion_modelo": float(np.mean([r["marcada_modelo"] for r in anom])),
            "modelo_score": score_metrics([r["y_true"] for r in sub], [r["score_modelo"] for r in sub]),
        }
    out["falsas_alarmas_por_indicador"] = {
        k: float(np.mean([k in r["indicadores"] for r in normals])) for k in RULE_KINDS + [MODEL_KIND]
    }
    return out


def run_experiment(cfg: ExperimentConfig) -> dict:
    all_records: list[dict] = []
    per_rep: list[dict] = []
    for rep in range(cfg.repeticiones):
        recs = run_repetition(cfg, rep)
        all_records.extend(recs)
        per_rep.append(_metrics_for(recs))

    def agg(path: list[str]) -> dict:
        vals = []
        for m in per_rep:
            v = m
            for p in path:
                v = v.get(p) if isinstance(v, dict) else None
                if v is None:
                    break
            vals.append(v if isinstance(v, (int, float)) else float("nan"))
        return summarize(vals)

    agregado = {
        "pipeline": {k: agg(["pipeline", k]) for k in ("far", "frr")},
        "solo_reglas": {k: agg(["solo_reglas", k]) for k in ("far", "frr")},
        "solo_modelo": {k: agg(["solo_modelo", k]) for k in ("far", "frr")},
        "modelo_score": {k: agg(["modelo_score", k]) for k in ("auc_roc", "average_precision", "eer")},
        "por_perfil": {
            perfil: {
                **{k: agg(["por_perfil", perfil, k]) for k in ("deteccion_pipeline", "deteccion_reglas", "deteccion_modelo")},
                **{k: agg(["por_perfil", perfil, "modelo_score", k]) for k in ("auc_roc", "average_precision", "eer")},
            }
            for perfil in cfg.perfiles
        },
        "falsas_alarmas_por_indicador": {
            k: agg(["falsas_alarmas_por_indicador", k]) for k in RULE_KINDS + [MODEL_KIND]
        },
    }

    return {"config": cfg.as_dict(), "agregado": agregado, "por_repeticion": per_rep, "registros": all_records}
