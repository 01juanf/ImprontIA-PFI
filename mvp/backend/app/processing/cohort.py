"""
Análisis poblacional al cierre de la evaluación (Incremento 16).

Hasta el Incremento 15 el Isolation Forest se entrenaba al finalizar cada sesión con las
sesiones finalizadas ANTES que ella: las primeras 20 no recibían análisis y cada una de
las siguientes se comparaba con una referencia distinta, que dependía del orden de
entrega. Ahora el modelo se aplica una sola vez, al cerrar la evaluación, sobre la
cohorte completa de sesiones finalizadas y con el mismo protocolo para todas:

- se entrena un único modelo con las métricas de todas las sesiones de la cohorte,
  ordenadas por identificador (el resultado no depende del orden de llegada);
- cada sesión se puntúa contra ese modelo (detección de anomalías transductiva: con
  contamination = 0,1, el modelo marca en torno al 10 % de la cohorte por diseño);
- si la cohorte tiene menos de MIN_SESSIONS_FOR_MODEL sesiones, ninguna se evalúa.

Función pura: recibe {session_id: métricas} y devuelve {session_id: AnomalyResult | None}.
"""
from typing import Optional

from .anomaly import AnomalyResult, fit_population_model, score_with_model


def analizar_cohorte(metrics_by_session: dict[str, dict[str, float]]) -> dict[str, Optional[AnomalyResult]]:
    ids = sorted(metrics_by_session)
    model = fit_population_model([metrics_by_session[i] for i in ids])
    if model is None:
        return {i: None for i in ids}
    return {i: score_with_model(model, metrics_by_session[i]) for i in ids}
