"""
Métricas de evaluación (Incremento 6).

Convención (ver equipo/investigacion/T05_evaluacion.md y cap. 18): la clase
"positiva" es la sesión ANÓMALA. Como en biometría "aceptar" significa
reconocer al usuario legítimo, se fija una única convención y se respeta en
todo el MVP:

- FAR (tasa de falsa aceptación) = tasa de ANOMALÍAS NO DETECTADAS:
  sesiones anómalas que el pipeline dejó pasar como normales  = FN / P.
- FRR (tasa de falso rechazo)   = tasa de FALSAS ALARMAS:
  sesiones normales que el pipeline marcó para revisión       = FP / N.
- EER: punto de la curva en el que FAR = FRR (requiere un score continuo).
- AUC-ROC (Fawcett 2006) y AP / average precision (Saito & Rehmsmeier 2015,
  recomendada con clases desbalanceadas).

El score continuo usado para ROC/EER/AP es el del Isolation Forest
(`-decision_function`: más alto = más atípico). Las reglas determinísticas
son binarias, así que para el pipeline completo solo hay un punto de
operación (FAR/FRR), no una curva.
"""
from typing import Sequence

import numpy as np
from sklearn.metrics import average_precision_score, roc_auc_score, roc_curve


def far_frr(y_true: Sequence[int], y_pred: Sequence[int]) -> dict[str, float]:
    """y_true / y_pred: 1 = anómala / marcada para revisión, 0 = normal / no marcada."""
    y_true = np.asarray(y_true, dtype=int)
    y_pred = np.asarray(y_pred, dtype=int)
    pos = y_true == 1
    neg = ~pos
    fn = int(np.sum(pos & (y_pred == 0)))
    fp = int(np.sum(neg & (y_pred == 1)))
    tp = int(np.sum(pos & (y_pred == 1)))
    tn = int(np.sum(neg & (y_pred == 0)))
    return {
        "far": fn / pos.sum() if pos.sum() else float("nan"),
        "frr": fp / neg.sum() if neg.sum() else float("nan"),
        "tp": tp, "fp": fp, "tn": tn, "fn": fn,
    }


def eer(y_true: Sequence[int], scores: Sequence[float]) -> tuple[float, float]:
    """
    Equal Error Rate a partir de la curva ROC. Devuelve (eer, umbral).

    Se recorre la curva ROC (FRR = fpr, FAR = 1 - tpr) y se interpola
    linealmente entre los dos puntos donde FAR - FRR cambia de signo.
    """
    fpr, tpr, thresholds = roc_curve(y_true, scores)
    fnr = 1 - tpr
    diff = fnr - fpr  # >0 al principio (umbral alto: se escapa todo), <=0 al final
    idx = np.where(diff <= 0)[0]
    if len(idx) == 0:
        return float(fnr[-1]), float(thresholds[-1])
    i = int(idx[0])
    if i == 0 or diff[i] == 0:
        return float((fpr[i] + fnr[i]) / 2), float(thresholds[i])
    # Interpolación entre i-1 (diff > 0) e i (diff < 0)
    w = diff[i - 1] / (diff[i - 1] - diff[i])
    e_fpr = fpr[i - 1] + w * (fpr[i] - fpr[i - 1])
    e_fnr = fnr[i - 1] + w * (fnr[i] - fnr[i - 1])
    thr = thresholds[i - 1] + w * (thresholds[i] - thresholds[i - 1]) if np.isfinite(thresholds[i - 1]) else thresholds[i]
    return float((e_fpr + e_fnr) / 2), float(thr)


def score_metrics(y_true: Sequence[int], scores: Sequence[float]) -> dict[str, float]:
    """AUC-ROC, AP y EER para un score continuo (más alto = más atípico)."""
    y_true = np.asarray(y_true, dtype=int)
    if len(set(y_true.tolist())) < 2:
        return {"auc_roc": float("nan"), "average_precision": float("nan"), "eer": float("nan")}
    e, _ = eer(y_true, scores)
    return {
        "auc_roc": float(roc_auc_score(y_true, scores)),
        "average_precision": float(average_precision_score(y_true, scores)),
        "eer": e,
    }


def summarize(values: Sequence[float]) -> dict[str, float]:
    """Media, desvío y percentiles 2.5/97.5 a través de repeticiones (ignora NaN)."""
    arr = np.asarray([v for v in values if v is not None and not np.isnan(v)], dtype=float)
    if len(arr) == 0:
        return {"mean": float("nan"), "std": float("nan"), "p2_5": float("nan"), "p97_5": float("nan"), "n": 0}
    return {
        "mean": float(arr.mean()),
        "std": float(arr.std(ddof=1)) if len(arr) > 1 else 0.0,
        "p2_5": float(np.percentile(arr, 2.5)),
        "p97_5": float(np.percentile(arr, 97.5)),
        "n": int(len(arr)),
    }
