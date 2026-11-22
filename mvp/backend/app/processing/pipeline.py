"""
Decisión del pipeline para UNA sesión, sin base de datos: métricas -> reglas
determinísticas + comparación poblacional (Isolation Forest) -> indicadores.

Antes del Incremento 6 esta lógica vivía inline en
routers/sessions.py::_run_processing. Se extrajo a una función pura para que
el endpoint `POST /sessions/{id}/end` y el script de evaluación
(scripts/evaluar.py) ejecuten exactamente el mismo código: así, lo que mide
la evaluación es el pipeline real del MVP y no una reimplementación.
"""
from dataclasses import dataclass
from typing import Optional

from .anomaly import AnomalyResult, PopulationModel, score_with_model
from .indicators import IndicatorDraft, generate_indicators, indicator_from_anomaly


@dataclass
class PipelineOutcome:
    drafts: list[IndicatorDraft]
    anomaly: Optional[AnomalyResult]  # None = población insuficiente, el modelo no se usó

    @property
    def needs_review(self) -> bool:
        # RF06/RF07: la sesión se prioriza para revisión si se generó al menos un indicador
        # que prioriza. Los informativos (p. ej. captura incompleta, Incremento 10) se
        # muestran al docente pero no marcan la sesión por sí solos.
        return any(d.prioritizes_review for d in self.drafts)


def evaluate_session(
    features: dict[str, float],
    pop_model: Optional[PopulationModel],
    rules: Optional[dict[str, bool]] = None,
) -> PipelineOutcome:
    # rules (Incremento 12): reglas del examen; None = comportamiento original (lo que usa
    # scripts/evaluar.py). No cambian el modelo poblacional, solo la relevancia de las reglas.
    drafts = generate_indicators(features, rules)
    anomaly = score_with_model(pop_model, features) if pop_model is not None else None
    anomaly_draft = indicator_from_anomaly(anomaly)
    if anomaly_draft:
        drafts.append(anomaly_draft)
    return PipelineOutcome(drafts=drafts, anomaly=anomaly)
