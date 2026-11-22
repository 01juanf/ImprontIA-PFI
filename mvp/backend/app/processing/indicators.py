"""
Generación de indicadores preliminares a partir de métricas ya calculadas.

Importante (RF10): esto NO decide si hubo fraude. Solo señala que una
métrica cruzó un umbral (o resultó atípica frente a la línea base
poblacional, ver anomaly.py), y guarda qué métrica/umbral lo originó para
que el docente pueda revisar la evidencia (RF09, RNF05, RNF06).

Los umbrales de esta sección son placeholders explícitos: la tesis (cap. 15,
"Decisiones técnicas que permanecen abiertas") aclara que se calibrarán con
datos reales de uso piloto, no están definidos todavía. Se centralizan acá
para que sean fáciles de encontrar y ajustar en un solo lugar.
"""
from dataclasses import dataclass, field
from typing import Optional

from .anomaly import AnomalyResult
from .rules import PERMITTED_NOTE, permitted_kinds

THRESHOLDS = {
    "paste_chars_total": 200.0,
    "tab_switch_count": 5.0,
    "focus_loss_duration_total_ms": 60_000.0,
    "std_dwell_time_ms_low": 5.0,  # tecleo demasiado uniforme (posible automatización)
}

# Nivel del indicador del modelo poblacional por PERCENTILES sobre la línea base
# (cap. 15, "Procesamiento e inteligencia artificial": las categorías se calibran
# con percentiles de la distribución del score en la muestra, no con un umbral
# absoluto). El modelo solo marca sesiones del lado atípico de su frontera, que con
# contamination=0.1 queda en torno al percentil 10 de la población; dentro de esas,
# las que caen en el 5 % más atípico de la línea base reciben nivel "alto" y el resto
# "medio". Las sesiones no marcadas equivalen a atipicidad "baja" y no generan
# indicador. Valor provisorio, a ajustar con datos piloto como los demás umbrales.
PERCENTILE_HIGH = 0.05

# Indicadores informativos: contextualizan la evidencia pero NO priorizan la sesión
# para revisión por sí solos (Incremento 10).
INFORMATIVE_KINDS = ("captura_incompleta",)


@dataclass
class IndicatorDraft:
    kind: str
    level: str  # "low" | "medium" | "high"
    description: str
    explanation: dict
    metric_names: list[str] = field(default_factory=list)  # para linkear IndicatorMetric
    # False = indicador informativo (contexto para la revisión): no marca por sí solo la
    # sesión como "requiere revisión". Ver pipeline.PipelineOutcome.needs_review.
    prioritizes_review: bool = True


def generate_indicators(features: dict[str, float], rules: Optional[dict[str, bool]] = None) -> list[IndicatorDraft]:
    """Reglas deterministas sobre eventos discretos/contables (cap. 15: 'marcas binarias').

    `rules` (Incremento 12): reglas del examen (ver rules.py). None o todas en False =
    comportamiento original, sin ningún cambio.
    """
    drafts: list[IndicatorDraft] = []

    if features.get("paste_chars_total", 0) > THRESHOLDS["paste_chars_total"]:
        drafts.append(IndicatorDraft(
            kind="paste_volume_alto",
            level="medium",
            description="El volumen de texto pegado durante la sesión supera el umbral de referencia.",
            explanation={
                "metric": "paste_chars_total",
                "value": features["paste_chars_total"],
                "threshold": THRESHOLDS["paste_chars_total"],
            },
            metric_names=["paste_chars_total"],
        ))

    if features.get("tab_switch_count", 0) > THRESHOLDS["tab_switch_count"]:
        drafts.append(IndicatorDraft(
            kind="cambios_pestana_frecuentes",
            level="medium",
            description="La cantidad de cambios de pestaña/ventana supera el umbral de referencia.",
            explanation={
                "metric": "tab_switch_count",
                "value": features["tab_switch_count"],
                "threshold": THRESHOLDS["tab_switch_count"],
            },
            metric_names=["tab_switch_count"],
        ))

    if features.get("focus_loss_duration_total_ms", 0) > THRESHOLDS["focus_loss_duration_total_ms"]:
        drafts.append(IndicatorDraft(
            kind="perdida_foco_prolongada",
            level="high",
            description="El tiempo total fuera de la pestaña de examen supera el umbral de referencia.",
            explanation={
                "metric": "focus_loss_duration_total_ms",
                "value": features["focus_loss_duration_total_ms"],
                "threshold": THRESHOLDS["focus_loss_duration_total_ms"],
            },
            metric_names=["focus_loss_duration_total_ms"],
        ))

    # Solo evalúa uniformidad si hay suficientes teclas para que el std sea significativo.
    if features.get("keydown_count", 0) >= 30 and features.get("std_dwell_time_ms", 999) < THRESHOLDS["std_dwell_time_ms_low"]:
        drafts.append(IndicatorDraft(
            kind="ritmo_tecleo_atipico",
            level="medium",
            description=(
                "La variabilidad del tiempo de pulsación de tecla es inusualmente baja "
                "respecto del umbral de referencia."
            ),
            explanation={
                "metric": "std_dwell_time_ms",
                "value": features["std_dwell_time_ms"],
                "threshold": THRESHOLDS["std_dwell_time_ms_low"],
            },
            metric_names=["std_dwell_time_ms"],
        ))

    # Integridad de la captura (cap. 15, "Captura de señales"): el agotamiento del buffer
    # local o una falla persistente de sincronización llegan como eventos propios del
    # cliente y se muestran al docente. No dicen nada sobre la conducta del estudiante
    # (una mala conexión no es un indicio), por eso es informativo y no prioriza.
    dropped = features.get("capture_dropped_events", 0)
    failures = features.get("sync_failure_count", 0)
    if dropped > 0 or failures > 0:
        partes = []
        if dropped > 0:
            partes.append(f"se descartaron {int(dropped)} eventos porque se agotó el buffer local del navegador")
        if failures > 0:
            partes.append(f"hubo {int(failures)} interrupción(es) prolongada(s) de la sincronización con el servidor")
        drafts.append(IndicatorDraft(
            kind="captura_incompleta",
            level="low",
            description=(
                "La captura de esta sesión puede estar incompleta: " + " y ".join(partes) + ". "
                "Las métricas e indicadores se calcularon sobre la evidencia que sí llegó. "
                "No es un indicio sobre la conducta del estudiante."
            ),
            explanation={
                "metric": "capture_dropped_events" if dropped > 0 else "sync_failure_count",
                "capture_dropped_events": dropped,
                "sync_failure_count": failures,
            },
            metric_names=[n for n, v in (("capture_dropped_events", dropped), ("sync_failure_count", failures)) if v > 0],
            prioritizes_review=False,
        ))

    return apply_exam_rules(drafts, rules)


def apply_exam_rules(drafts: list[IndicatorDraft], rules: Optional[dict[str, bool]]) -> list[IndicatorDraft]:
    """Incremento 12 (R2): si las reglas del examen permiten la conducta, el indicador se
    conserva (trazabilidad) pero con nivel bajo, la aclaración y sin priorizar la sesión."""
    allowed = permitted_kinds(rules)
    if not allowed:
        return drafts
    for d in drafts:
        if d.kind in allowed:
            d.level = "low"
            d.prioritizes_review = False
            d.description = f"{d.description} Esto está {PERMITTED_NOTE}."
            d.explanation = {**d.explanation, "permitido_por_reglas": True, "nota": PERMITTED_NOTE}
    return drafts


def level_from_percentile(population_percentile: Optional[float]) -> str:
    """Nivel por posición relativa en la línea base (no por un corte absoluto del score)."""
    if population_percentile is not None and population_percentile <= PERCENTILE_HIGH:
        return "high"
    return "medium"


def indicator_from_anomaly(result: Optional[AnomalyResult]) -> Optional[IndicatorDraft]:
    """
    Traduce el resultado del modelo poblacional (anomaly.py) en un indicador,
    si corresponde. Devuelve None si no hubo suficiente población para
    entrenar el modelo, o si la sesión no resultó atípica.
    """
    if result is None or not result.is_anomalous:
        return None

    level = level_from_percentile(result.population_percentile)
    top = result.top_features

    return IndicatorDraft(
        kind="atipico_modelo_poblacional",
        level=level,
        description=(
            # Incremento 16: el modelo corre una sola vez, al cerrar la evaluación, sobre la
            # cohorte completa de sesiones finalizadas (processing/cohort.py).
            "El patrón de teclado/mouse de esta sesión resultó atípico frente al resto de las "
            "sesiones de esta evaluación, analizadas en conjunto al cerrarla (comparación con la "
            "cohorte, no con un perfil personal)."
        ),
        explanation={
            "model": "isolation_forest_poblacional",
            # Se conserva para trazabilidad, pero el dashboard NO lo muestra (cap. 15: no se
            # expone al docente el valor crudo del score): muestra el nivel y la posición
            # relativa en la línea base.
            "anomaly_score": result.anomaly_score,
            "population_percentile": result.population_percentile,
            "population_size": result.population_size,
            "percentile_high_cut": PERCENTILE_HIGH,
            "top_features": top,
        },
        metric_names=[f["metric"] for f in top],
    )
