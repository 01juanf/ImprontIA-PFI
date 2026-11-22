"""
Detección de anomalías sobre línea base poblacional.

Cap. 15, sección "Procesamiento e inteligencia artificial": el componente de
IA es requisito del MVP, no una extensión postergable. Se compara cada
sesión contra la distribución agregada de la muestra general de sesiones
disponibles (línea base poblacional/de cohorte) — NUNCA contra el historial
propio del estudiante, porque el MVP no puede garantizar ese historial y
además tomaría el patrón habitual de cada quien como su propia referencia.

Solo las métricas CONTINUAS entran acá (tiempos de tecla, velocidad de
mouse). Los eventos discretos (paste, cambio de pestaña, pérdida de foco)
ya se cubren con reglas de umbral en indicators.py y se reportan como
marcas binarias, tal como distingue cap. 15.

Con pocas sesiones el modelo no tiene significado estadístico — ver
MIN_SESSIONS_FOR_MODEL. Este es exactamente el estado esperado hasta que
existan datos de sesiones piloto reales (cap. 15: los resultados numéricos
de validación se reportarán en el entregable final, una vez recolectados).
"""
from dataclasses import dataclass, field
from statistics import mean, pstdev
from typing import Optional

from sklearn.ensemble import IsolationForest

CONTINUOUS_METRICS = [
    "mean_dwell_time_ms",
    "std_dwell_time_ms",
    "mean_flight_time_ms",
    "mean_mouse_speed_px_ms",
    "std_mouse_speed_px_ms",
]

# No es un placeholder arbitrario: sklearn fija la altura máxima de cada
# árbol en ceil(log2(max_samples)), así que con menos de ~20 muestras el
# Isolation Forest queda tan playo que ni siquiera aísla un outlier extremo
# en todas sus dimensiones (verificado empíricamente: con población=9 un
# valor 3-10x fuera de rango en las 5 features seguía dando "normal"; a
# partir de 20 se separa de forma consistente). Sigue siendo un mínimo
# técnico para que el algoritmo funcione, no una calibración estadística
# real — esa calibración depende de datos de sesiones piloto (cap. 15).
MIN_SESSIONS_FOR_MODEL = 20


@dataclass
class AnomalyResult:
    is_anomalous: bool
    anomaly_score: float  # de IsolationForest.decision_function: más bajo = más atípico
    top_features: list[dict]
    # Incremento 10: posición relativa de la sesión en la línea base. Proporción de las
    # sesiones de la población con un score igual o más atípico que el de esta sesión
    # (0 = más atípica que todas; 0,05 = dentro del 5 % más atípico). Con ella se fija el
    # NIVEL del indicador por percentiles sobre la muestra (cap. 15), no por un corte absoluto.
    population_percentile: Optional[float] = None
    population_size: int = 0


def percentile_rank(score: float, reference_scores: list[float]) -> float:
    """
    Proporción de `reference_scores` que son <= `score` (más bajo = más atípico).

    Es el percentil empírico de la sesión dentro de la distribución de scores de la
    línea base: 0,03 significa que solo el 3 % de las sesiones de la población es
    igual o más atípica que ella.
    """
    if not reference_scores:
        return float("nan")
    return sum(1 for s in reference_scores if s <= score) / len(reference_scores)


def _top_deviating_features(
    x_target: list[float], population: list[list[float]], metric_names: list[str], top_n: int = 2
) -> list[dict]:
    """Explicabilidad (RNF06): qué features se alejan más de la media poblacional, vía z-score."""
    deviations = []
    for i, name in enumerate(metric_names):
        col = [row[i] for row in population]
        mu = mean(col)
        sigma = pstdev(col) if len(col) > 1 else 0.0
        z = (x_target[i] - mu) / sigma if sigma > 0 else 0.0
        deviations.append({"metric": name, "value": x_target[i], "population_mean": mu, "z_score": z})
    deviations.sort(key=lambda d: abs(d["z_score"]), reverse=True)
    return deviations[:top_n]


@dataclass
class PopulationModel:
    """
    Isolation Forest ya entrenado sobre una población de sesiones, más lo
    necesario para explicar un score (columnas activas y matriz de entrenamiento).

    Separar "entrenar" de "puntuar" (Incremento 6) permite que el script de
    evaluación (scripts/evaluar.py) puntúe muchas sesiones contra la misma
    población sin reentrenar 200 árboles por sesión. Como el modelo usa
    random_state fijo, entrenar una vez y puntuar N veces da exactamente el
    mismo resultado que llamar N veces a score_against_population (hay un
    test que lo verifica).
    """

    model: IsolationForest
    active_metrics: list[str]
    X: list[list[float]]
    # Scores de la propia población de entrenamiento: la distribución de referencia para
    # ubicar a una sesión nueva por percentiles (Incremento 10).
    train_scores: list[float] = field(default_factory=list)


def fit_population_model(population_metrics: list[dict[str, float]]) -> Optional[PopulationModel]:
    """
    Devuelve None si la población disponible es menor a MIN_SESSIONS_FOR_MODEL
    o si ninguna métrica continua tiene varianza (no hay modelo que entrenar).
    """
    if len(population_metrics) < MIN_SESSIONS_FOR_MODEL:
        return None

    # Una feature constante en la población (ej. sin eventos de mouse) no aporta
    # ninguna señal y solo diluye las divisiones aleatorias del Isolation Forest
    # (con pocas muestras, esto puede hacer que un outlier real pase desapercibido).
    active_metrics = [
        name for name in CONTINUOUS_METRICS
        if pstdev([m.get(name, 0.0) for m in population_metrics]) > 1e-9
    ]
    if not active_metrics:
        return None

    X = [[m.get(name, 0.0) for name in active_metrics] for m in population_metrics]
    model = IsolationForest(n_estimators=200, contamination=0.1, random_state=0)
    model.fit(X)
    train_scores = [float(v) for v in model.decision_function(X)]
    return PopulationModel(model=model, active_metrics=active_metrics, X=X, train_scores=train_scores)


def score_with_model(pop_model: PopulationModel, target_metrics: dict[str, float]) -> AnomalyResult:
    x_target = [target_metrics.get(name, 0.0) for name in pop_model.active_metrics]
    prediction = pop_model.model.predict([x_target])[0]  # -1 = anómalo, 1 = normal
    score = float(pop_model.model.decision_function([x_target])[0])

    return AnomalyResult(
        is_anomalous=bool(prediction == -1),  # numpy.bool_ -> bool nativo (evita sorpresas con `is True`)
        anomaly_score=score,
        top_features=_top_deviating_features(x_target, pop_model.X, pop_model.active_metrics),
        population_percentile=percentile_rank(score, pop_model.train_scores),
        population_size=len(pop_model.X),
    )


def score_against_population(
    target_metrics: dict[str, float],
    population_metrics: list[dict[str, float]],
) -> Optional[AnomalyResult]:
    """
    Devuelve None si la población disponible es menor a MIN_SESSIONS_FOR_MODEL
    (el modelo no se entrena ni se usa: no hay indicador de IA para esta sesión).
    """
    pop_model = fit_population_model(population_metrics)
    if pop_model is None:
        return None
    return score_with_model(pop_model, target_metrics)
