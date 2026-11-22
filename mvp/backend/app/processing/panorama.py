"""
Panorama agregado de una evaluación (Incremento 12, R1).

Función pura: resume métricas e indicadores YA calculados por el pipeline (no
recalcula nada ni toca el modelo). Le da al docente una vista de cómo transcurrió
la evaluación en conjunto, útil aunque ninguna sesión requiera revisión.
"""
from collections import Counter
from typing import Optional

import numpy as np

# Métricas de proceso que se resumen (nombres de features.py).
PANORAMA_METRICS = (
    "session_wall_duration_ms",  # duración real: inicio a fin según el servidor (Incremento 16)
    "session_duration_ms",       # período con eventos registrados (primer a último evento)
    "idle_ratio",
    "paste_chars_total",
    "tab_switch_count",
    "focus_loss_duration_total_ms",
)

MODEL_KIND = "atipico_modelo_poblacional"


def _summary(values: list[float]) -> dict:
    if not values:
        return {"n": 0, "mediana": None, "p25": None, "p75": None}
    p25, med, p75 = np.percentile(np.asarray(values, dtype=float), [25, 50, 75])
    return {"n": len(values), "mediana": float(med), "p25": float(p25), "p75": float(p75)}


def compute_panorama(
    metrics_by_session: dict[str, dict[str, float]],
    indicators: list[dict],
    needs_review: Optional[dict[str, bool]] = None,
) -> dict:
    """
    metrics_by_session: {session_id: {metric_name: value}} de las sesiones FINALIZADAS
        (solo métricas de sesión completa, item_ref = None).
    indicators: [{"session_id", "kind", "explanation"}] de esas mismas sesiones.
    needs_review: {session_id: bool} (opcional).
    """
    session_ids = set(metrics_by_session)
    n = len(session_ids)

    metricas = []
    for name in PANORAMA_METRICS:
        vals = [m[name] for m in metrics_by_session.values() if name in m]
        metricas.append({"metric": name, **_summary(vals)})

    sesiones_por_tipo: dict[str, set] = {}
    permitidas_por_tipo: dict[str, set] = {}
    modelo_sesiones: set = set()
    top_counter: Counter = Counter()
    for ind in indicators:
        sid = ind["session_id"]
        if sid not in session_ids:
            continue
        kind = ind["kind"]
        expl = ind.get("explanation") or {}
        sesiones_por_tipo.setdefault(kind, set()).add(sid)
        if expl.get("permitido_por_reglas"):
            permitidas_por_tipo.setdefault(kind, set()).add(sid)
        if kind == MODEL_KIND and sid not in modelo_sesiones:
            modelo_sesiones.add(sid)
            for f in expl.get("top_features", []) or []:
                if f.get("metric"):
                    top_counter[f["metric"]] += 1

    indicadores = sorted(
        (
            {
                "kind": k,
                "sesiones": len(v),
                "permitidas_por_reglas": len(permitidas_por_tipo.get(k, ())),
                "porcentaje": (len(v) / n) if n else 0.0,
            }
            for k, v in sesiones_por_tipo.items()
        ),
        key=lambda d: (-d["sesiones"], d["kind"]),
    )

    return {
        "n_sesiones": n,
        "sesiones_requieren_revision": sum(1 for s in session_ids if (needs_review or {}).get(s)),
        "metricas": metricas,
        "indicadores": indicadores,
        "modelo": {
            "sesiones_marcadas": len(modelo_sesiones),
            "porcentaje": (len(modelo_sesiones) / n) if n else 0.0,
            "metricas_frecuentes": [
                {"metric": m, "sesiones": c}
                for m, c in sorted(top_counter.items(), key=lambda kv: (-kv[1], kv[0]))
            ],
        },
    }
