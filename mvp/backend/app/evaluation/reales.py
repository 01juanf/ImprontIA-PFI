"""
Análisis de sesiones de SIMULACIÓN etiquetadas (Fase 2, P03).

Es el mismo procedimiento del Incremento 6 (`experiment.py` + `metrics.py`),
pero sobre sesiones rendidas por personas que declararon una condición
simulada (`sessions.condicion_simulacion`, ver docs/simulaciones/protocolo.md).

Dos partes, ambas puras (sin acceso a la base):

1. `registros_desde_sesiones`: arma las filas del CSV de exportación a partir
   de las sesiones ya procesadas. Sin datos personales: el código de
   participante se reemplaza por un alias (P01, P02...) y no se exportan
   fechas, contexto, eventos crudos ni textos.
2. `analizar`: calcula FAR, FRR, AUC-ROC, AP y EER con las funciones de
   `metrics.py`:
   - **Operación:** lo que el sistema marcó de verdad al finalizar cada sesión
     (`needs_review`), contra la etiqueta.
   - **Modelo, fuera de línea:** score continuo del Isolation Forest para cada
     sesión, entrenado solo con sesiones `normal` y sin la sesión evaluada
     (dejar una afuera). Con `excluir_participante=True` se excluyen además
     todas las sesiones de la misma persona (partición por participante, cap. 18).
     Usa `fit_population_model` / `score_with_model` sin cambios.
   - Intervalos por remuestreo de participantes (bootstrap por grupo).

Convención (metrics.py): positiva = sesión con condición distinta de `normal`.
FAR = anomalías no detectadas; FRR = falsas alarmas.
"""
from __future__ import annotations

import math
from typing import Iterable, Optional

import numpy as np

from ..processing.anomaly import CONTINUOUS_METRICS, fit_population_model, score_with_model
from ..simulacion import CONDICION_NORMAL, CONDICIONES
from .experiment import MODEL_KIND, RULE_KINDS
from .metrics import far_frr, score_metrics

# Columnas fijas del CSV, en orden. Después van las métricas de sesión completa (orden alfabético).
COLUMNAS_BASE = [
    "sesion", "evaluacion", "participante", "orden_participante", "condicion", "y_true",
    "marcada", "marcada_reglas", "marcada_modelo", "indicadores", "n_eventos", "duracion_s",
]


def _alias(valores: Iterable[str], prefijo: str) -> dict[str, str]:
    """Alias estable por orden de aparición (no reversible desde el CSV)."""
    out: dict[str, str] = {}
    for v in valores:
        if v not in out:
            out[v] = f"{prefijo}{len(out) + 1:02d}"
    return out


def registros_desde_sesiones(sesiones: list[dict], incluir_sin_etiqueta: bool = False) -> list[dict]:
    """
    `sesiones`: una entrada por sesión FINALIZADA, ordenadas por inicio, con
    `exam_id`, `participant_id`, `condicion` (o None), `needs_review`,
    `indicadores` (lista de `(kind, level)`), `metricas` (dict de sesión completa),
    `n_eventos` y `duracion_s`.
    """
    if not incluir_sin_etiqueta:
        sesiones = [s for s in sesiones if s.get("condicion")]
    alias_p = _alias((s["participant_id"] for s in sesiones), "P")
    alias_e = _alias((s["exam_id"] for s in sesiones), "E")
    contador: dict[str, int] = {}
    filas = []
    for i, s in enumerate(sesiones, start=1):
        p = alias_p[s["participant_id"]]
        contador[p] = contador.get(p, 0) + 1
        cond = s.get("condicion") or ""
        kinds = [k for k, _ in s["indicadores"]]
        # Una regla "permitida por las reglas del examen" queda en nivel bajo y no prioriza (R2).
        reglas_activas = [k for k, lvl in s["indicadores"] if k in RULE_KINDS and lvl != "low"]
        fila = {
            "sesion": f"S{i:03d}",
            "evaluacion": alias_e[s["exam_id"]],
            "participante": p,
            "orden_participante": contador[p],
            "condicion": cond,
            "y_true": "" if not cond else int(cond != CONDICION_NORMAL),
            "marcada": int(bool(s["needs_review"])),
            "marcada_reglas": int(bool(reglas_activas)),
            "marcada_modelo": int(MODEL_KIND in kinds),
            "indicadores": ";".join(sorted(set(kinds))),
            "n_eventos": int(s["n_eventos"]),
            "duracion_s": round(float(s["duracion_s"]), 1) if s.get("duracion_s") is not None else "",
        }
        for name in sorted(s["metricas"]):
            fila[name] = s["metricas"][name]
        filas.append(fila)
    return filas


def _float(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return float("nan")


def scores_fuera_de_linea(filas: list[dict], excluir_participante: bool = False) -> list[float]:
    """Score del IF (más alto = más atípico) por fila; NaN si no hay población suficiente."""
    metricas = [{m: _float(f.get(m)) for m in CONTINUOUS_METRICS} for f in filas]
    scores = []
    for i, f in enumerate(filas):
        poblacion = [
            metricas[j] for j, g in enumerate(filas)
            if j != i and g["condicion"] == CONDICION_NORMAL
            and not (excluir_participante and g["participante"] == f["participante"])
        ]
        modelo = fit_population_model(poblacion)
        if modelo is None:
            scores.append(float("nan"))
        else:
            scores.append(-score_with_model(modelo, metricas[i]).anomaly_score)
    return scores


def _metricas(filas: list[dict], scores: list[float]) -> dict:
    y = [int(f["y_true"]) for f in filas]
    op = far_frr(y, [int(f["marcada"]) for f in filas])
    con_score = [(yy, s) for yy, s in zip(y, scores) if not math.isnan(s)]
    modelo = score_metrics([a for a, _ in con_score], [b for _, b in con_score]) if con_score else \
        {"auc_roc": float("nan"), "average_precision": float("nan"), "eer": float("nan")}
    return {
        "n": len(filas),
        "n_normales": y.count(0),
        "n_anomalas": y.count(1),
        "operacion": op,
        "modelo_score": {**modelo, "n_con_score": len(con_score)},
    }


def _bootstrap(filas: list[dict], scores: list[float], n_boot: int, semilla: int) -> dict:
    """Intervalo 95 % remuestreando PARTICIPANTES con reposición (cap. 18)."""
    participantes = sorted({f["participante"] for f in filas})
    if len(participantes) < 2 or n_boot <= 0:
        return {}
    por_p = {p: [i for i, f in enumerate(filas) if f["participante"] == p] for p in participantes}
    rng = np.random.default_rng(semilla)
    acum: dict[str, list[float]] = {"far": [], "frr": [], "auc_roc": [], "average_precision": [], "eer": []}
    for _ in range(n_boot):
        idx = [i for p in rng.choice(participantes, size=len(participantes), replace=True) for i in por_p[p]]
        m = _metricas([filas[i] for i in idx], [scores[i] for i in idx])
        acum["far"].append(m["operacion"]["far"])
        acum["frr"].append(m["operacion"]["frr"])
        for k in ("auc_roc", "average_precision", "eer"):
            acum[k].append(m["modelo_score"][k])
    out = {}
    for k, vals in acum.items():
        arr = np.asarray([v for v in vals if not math.isnan(v)], dtype=float)
        out[k] = {"p2_5": float(np.percentile(arr, 2.5)), "p97_5": float(np.percentile(arr, 97.5)),
                  "n_validas": int(len(arr))} if len(arr) else {"p2_5": float("nan"), "p97_5": float("nan"), "n_validas": 0}
    return out


def analizar(filas: list[dict], excluir_participante: bool = False, n_boot: int = 1000, semilla: int = 2026) -> dict:
    """Métricas globales, por condición y avisos. Solo usa las filas con condición."""
    filas = [f for f in filas if f.get("condicion") in CONDICIONES]
    scores = scores_fuera_de_linea(filas, excluir_participante)
    resultado = {
        "config": {"excluir_participante": excluir_participante, "n_boot": n_boot, "semilla": semilla},
        "participantes": len({f["participante"] for f in filas}),
        "conteo_por_condicion": {c: sum(f["condicion"] == c for f in filas) for c in CONDICIONES},
        "global": _metricas(filas, scores) if filas else {},
        "intervalos": _bootstrap(filas, scores, n_boot, semilla) if filas else {},
        "por_condicion": {},
        "scores": scores,
        "avisos": [],
    }
    normales = [i for i, f in enumerate(filas) if f["condicion"] == CONDICION_NORMAL]
    for c in CONDICIONES:
        if c == CONDICION_NORMAL:
            continue
        idx = normales + [i for i, f in enumerate(filas) if f["condicion"] == c]
        if len(idx) == len(normales):
            continue
        m = _metricas([filas[i] for i in idx], [scores[i] for i in idx])
        anom = [filas[i] for i in idx if filas[i]["condicion"] == c]
        m["detectadas_operacion"] = sum(int(f["marcada"]) for f in anom)
        m["detectadas_reglas"] = sum(int(f["marcada_reglas"]) for f in anom)
        m["detectadas_modelo"] = sum(int(f["marcada_modelo"]) for f in anom)
        resultado["por_condicion"][c] = m

    av = resultado["avisos"]
    if not filas:
        av.append("No hay sesiones etiquetadas.")
    if len(normales) <= 20:
        av.append(f"Solo hay {len(normales)} sesiones normales: el modelo necesita al menos 21 "
                  "(20 sin la evaluada) y sin modelo no hay AUC, AP ni EER.")
    if excluir_participante:
        av.append("Partición por participante: cada sesión se puntúa con un modelo entrenado sin "
                  "ninguna sesión de la misma persona.")
    if resultado["participantes"] < 5:
        av.append(f"Solo {resultado['participantes']} participante(s): los intervalos por remuestreo de "
                  "participantes no son interpretables; informar las cifras como exploratorias.")
    if any(math.isnan(s) for s in scores):
        av.append(f"{sum(math.isnan(s) for s in scores)} sesión(es) sin score del modelo (población insuficiente).")
    return resultado


def fmt(v: Optional[float], pct: bool = False) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "—"
    return f"{v * 100:.1f} %".replace(".", ",") if pct else f"{v:.3f}".replace(".", ",")
