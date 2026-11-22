"""
Evaluación reproducible del pipeline de ImprontIA sobre DATOS SINTÉTICOS
(Incremento 6, ver mvp/docs/bitacora.md).

Valida el PROCEDIMIENTO de evaluación (generar sesiones etiquetadas -> pasar
por el pipeline real -> calcular FAR, FRR, AUC-ROC, AP y EER), no el
desempeño real del sistema: los resultados con sesiones humanas dependen
del piloto (cap. 18). Ver app/evaluation/synthetic.py para los parámetros
y perfiles, y app/evaluation/metrics.py para la convención FAR/FRR.

Uso (desde mvp/backend):

    python -m scripts.evaluar                       # configuración por defecto
    python -m scripts.evaluar --repeticiones 50 --dificultad 2
    python -m scripts.evaluar --contaminacion 0.1   # población con 10 % de anómalas
    python -m scripts.evaluar --sin-barrido --salida /tmp/eval
    python -m scripts.evaluar --protocolo cierre    # análisis de la cohorte al cierre (Incremento 16)

Protocolo (--protocolo):
- `poblacion_previa` (por defecto, el del Incremento 6): el modelo se entrena con una población
  previa de la evaluación y las sesiones de prueba se puntúan fuera de muestra. Es el que
  generó resultados_sinteticos.md; ya NO es el protocolo del MVP.
- `cierre`: el del MVP desde el Incremento 16 (processing/cohort.py). La cohorte (población +
  prueba) se analiza una sola vez, con un único modelo, y cada sesión se puntúa contra él. Las
  salidas llevan el sufijo `_inc16` (configurable con --sufijo) para no pisar las anteriores.
  La comparación del aporte del modelo con prevalencias realistas está en scripts/aporte_modelo.py.

Salidas (por defecto en mvp/docs/evaluacion/):
- resultados_sinteticos.md    reporte legible (config + tablas + advertencias)
- resultados_sinteticos.json  config + métricas agregadas y por repetición
- sesiones_sinteticas.csv     un registro por sesión de prueba (sin eventos)
- roc_modelo.csv              curva ROC agregada del score del Isolation Forest
- barrido_dificultad.csv      AUC/EER/detección de `ritmo_distinto` vs. dificultad
"""
import argparse
import csv
import json
import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import sklearn  # noqa: E402
from sklearn.metrics import roc_curve  # noqa: E402

from app.evaluation.experiment import PROTOCOLOS, ExperimentConfig, run_experiment  # noqa: E402
from app.evaluation.synthetic import SyntheticParams  # noqa: E402
from app.processing.anomaly import MIN_SESSIONS_FOR_MODEL  # noqa: E402
from app.processing.indicators import THRESHOLDS  # noqa: E402

DEFAULT_OUT = Path(__file__).resolve().parent.parent.parent / "docs" / "evaluacion"


def pct(s: dict) -> str:
    if s["n"] == 0:
        return "—"
    return f"{100 * s['mean']:.1f} % ± {100 * s['std']:.1f} [{100 * s['p2_5']:.1f}–{100 * s['p97_5']:.1f}]"


def num(s: dict) -> str:
    if s["n"] == 0:
        return "—"
    return f"{s['mean']:.3f} ± {s['std']:.3f} [{s['p2_5']:.3f}–{s['p97_5']:.3f}]"


def pooled_roc(records: list[dict], perfil: str | None = None) -> list[tuple[float, float, float]]:
    sub = [r for r in records if not np.isnan(r["score_modelo"]) and (perfil is None or r["perfil"] in ("normal", perfil))]
    y = [r["y_true"] for r in sub]
    s = [r["score_modelo"] for r in sub]
    fpr, tpr, thr = roc_curve(y, s)
    return list(zip(fpr.tolist(), tpr.tolist(), thr.tolist()))


def run_sweep(base: ExperimentConfig, levels: list[float]) -> list[dict]:
    rows = []
    for k in levels:
        cfg = replace(base, perfiles=["ritmo_distinto"], params=replace(base.params, dificultad=k))
        a = run_experiment(cfg)["agregado"]
        p = a["por_perfil"]["ritmo_distinto"]
        rows.append({
            "dificultad": k,
            "auc_mean": p["auc_roc"]["mean"], "auc_std": p["auc_roc"]["std"],
            "eer_mean": p["eer"]["mean"], "eer_std": p["eer"]["std"],
            "ap_mean": p["average_precision"]["mean"],
            "deteccion_modelo_mean": p["deteccion_modelo"]["mean"],
            "frr_modelo_mean": a["solo_modelo"]["frr"]["mean"],
        })
    return rows


def write_report(out: Path, res: dict, sweep: list[dict], sensibilidad: dict | None, sufijo: str = "") -> None:
    cfg = res["config"]
    a = res["agregado"]
    p = cfg["params"]
    L = []
    w = L.append
    w("# Evaluación del pipeline con datos sintéticos")
    w("")
    w(f"_Generado por `scripts/evaluar.py` el {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} "
      f"(scikit-learn {sklearn.__version__}, numpy {np.__version__}). No editar a mano: regenerar con el script._")
    w("")
    w("> **Advertencia.** Estos números provienen de sesiones **sintéticas** generadas con parámetros elegidos "
      "para ejercitar el pipeline, no calibrados con personas reales. Validan que el **procedimiento** de "
      "evaluación funciona de punta a punta (eventos → métricas → reglas + Isolation Forest → FAR/FRR/AUC/EER) "
      "y muestran cómo se comporta el pipeline frente a anomalías de forma conocida. **No son resultados del "
      "piloto ni una estimación del desempeño real** con estudiantes.")
    w("")
    w("## Convención de métricas")
    w("")
    w("Clase positiva = sesión anómala. **FAR** = tasa de anomalías no detectadas (FN/P). "
      "**FRR** = tasa de falsas alarmas (FP/N). **EER** = punto donde FAR = FRR. "
      "AUC-ROC, AP (average precision) y EER se calculan sobre el score continuo del Isolation Forest "
      "(`-decision_function`); las reglas son binarias y solo aportan un punto de operación. "
      "Cada celda: media ± desvío entre repeticiones [percentiles 2,5–97,5].")
    w("")
    w("## Protocolo y parámetros")
    w("")
    if cfg.get("protocolo") == "cierre":
        w("- Protocolo del modelo: **análisis de la cohorte al cierre** (Incremento 16, `processing/cohort.py`): "
          "la cohorte es la población más las sesiones de prueba; se entrena un único Isolation Forest con todas "
          "y cada sesión de prueba se puntúa contra ese modelo (transductivo). Prevalencia de anómalas en la cohorte: "
          f"**{100 * cfg['n_anomalas_test'] / (cfg['n_poblacion'] + cfg['n_normales_test'] + cfg['n_anomalas_test']):.0f} %**.")
    else:
        w("- Protocolo del modelo: **población previa** (Incremento 6): el Isolation Forest se entrena con la "
          "población y las sesiones de prueba se puntúan fuera de muestra. Desde el Incremento 16 el MVP usa el "
          "análisis al cierre (`--protocolo cierre`).")
    w(f"- Repeticiones: **{cfg['repeticiones']}** (semillas {cfg['semilla_base']}…{cfg['semilla_base'] + cfg['repeticiones'] - 1}).")
    w(f"- Población (línea base de la evaluación): **{cfg['n_poblacion']}** sesiones, contaminación "
      f"{100 * cfg['contaminacion_poblacion']:.0f} % (mínimo técnico del modelo: {MIN_SESSIONS_FOR_MODEL}).")
    w(f"- Prueba por repetición: **{cfg['n_normales_test']}** normales + **{cfg['n_anomalas_test']}** anómalas, "
      f"repartidas en partes iguales entre: {', '.join(cfg['perfiles'])}.")
    w(f"- Pipeline evaluado tal como está en el MVP (sin ajustar con las etiquetas): umbrales {THRESHOLDS}; "
      "Isolation Forest `n_estimators=200`, `contamination=0.1`, `random_state=0`.")
    w(f"- Población normal: dwell ~ N({p['dwell_mu']}, {p['dwell_sd_between']}) ms entre participantes, "
      f"desvío intra-sesión U{tuple(p['dwell_sd_within_range'])}; flight ~ N({p['flight_mu']}, {p['flight_sd_between']}) ms, "
      f"intra U{tuple(p['flight_sd_within_range'])}; {p['keys_range'][0]}–{p['keys_range'][1]} pulsaciones; "
      f"mouse ~ N({p['mouse_speed_mu']}, {p['mouse_speed_sd_between']}) px/ms (CV intra {p['mouse_speed_cv_within']}); "
      f"cambios de pestaña ~ Poisson({p['tab_switch_lambda']}) con duración media {p['tab_hidden_mean_ms']:.0f} ms; "
      f"pegado chico con prob. {p['paste_prob']} ({p['paste_chars_range'][0]}–{p['paste_chars_range'][1]} caracteres).")
    w(f"- Dificultad de `ritmo_distinto`: **{p['dificultad']}** desvíos poblacionales en dwell, flight y velocidad de mouse.")
    w("")
    w("## Resultados globales")
    w("")
    w("| Componente | FAR (anomalías no detectadas) | FRR (falsas alarmas) |")
    w("|---|---|---|")
    w(f"| Pipeline completo (reglas ∨ modelo) | {pct(a['pipeline']['far'])} | {pct(a['pipeline']['frr'])} |")
    w(f"| Solo reglas determinísticas | {pct(a['solo_reglas']['far'])} | {pct(a['solo_reglas']['frr'])} |")
    w(f"| Solo Isolation Forest | {pct(a['solo_modelo']['far'])} | {pct(a['solo_modelo']['frr'])} |")
    w("")
    w("Score continuo del Isolation Forest (todas las anomalías vs. normales):")
    w("")
    w("| AUC-ROC | AP | EER |")
    w("|---|---|---|")
    ms = a["modelo_score"]
    w(f"| {num(ms['auc_roc'])} | {num(ms['average_precision'])} | {num(ms['eer'])} |")
    w("")
    w("## Por perfil de anomalía")
    w("")
    w("| Perfil | Detección pipeline | Detección reglas | Detección modelo | AUC-ROC modelo | EER modelo |")
    w("|---|---|---|---|---|---|")
    for perfil, d in a["por_perfil"].items():
        w(f"| `{perfil}` | {pct(d['deteccion_pipeline'])} | {pct(d['deteccion_reglas'])} | {pct(d['deteccion_modelo'])} "
          f"| {num(d['auc_roc'])} | {num(d['eer'])} |")
    w("")
    w("Falsas alarmas sobre sesiones normales, por indicador:")
    w("")
    w("| Indicador | Tasa sobre normales |")
    w("|---|---|")
    for k, s in a["falsas_alarmas_por_indicador"].items():
        w(f"| `{k}` | {pct(s)} |")
    w("")
    if sweep:
        w("## Barrido de dificultad (`ritmo_distinto`, solo modelo)")
        w("")
        w("Separación entre la sesión anómala y la población, en desvíos poblacionales. Muestra cuánto tiene que "
          "diferir una sesión para que el Isolation Forest la distinga, sin señales discretas que la delaten.")
        w("")
        w("| Dificultad (σ) | AUC-ROC | EER | Detección modelo | FRR modelo |")
        w("|---|---|---|---|---|")
        for r in sweep:
            w(f"| {r['dificultad']:g} | {r['auc_mean']:.3f} ± {r['auc_std']:.3f} | {r['eer_mean']:.3f} ± {r['eer_std']:.3f} "
              f"| {100 * r['deteccion_modelo_mean']:.1f} % | {100 * r['frr_modelo_mean']:.1f} % |")
        w("")
    if sensibilidad:
        sa = sensibilidad["agregado"]
        w(f"## Sensibilidad: población contaminada ({100 * sensibilidad['config']['contaminacion_poblacion']:.0f} % de anómalas)")
        w("")
        w("Misma configuración, pero la línea base incluye sesiones anómalas (como ocurriría en un examen real).")
        w("")
        w("| Componente | FAR | FRR |")
        w("|---|---|---|")
        w(f"| Pipeline completo | {pct(sa['pipeline']['far'])} | {pct(sa['pipeline']['frr'])} |")
        w(f"| Solo Isolation Forest | {pct(sa['solo_modelo']['far'])} | {pct(sa['solo_modelo']['frr'])} |")
        w(f"| AUC-ROC modelo (`ritmo_distinto`) | {num(sa['por_perfil']['ritmo_distinto']['auc_roc'])} | |")
        w("")
    w("## Lectura e interpretación (para el cap. 17/18)")
    w("")
    if cfg.get("protocolo") == "cierre":
        n_coh = cfg["n_poblacion"] + cfg["n_normales_test"] + cfg["n_anomalas_test"]
        w(f"- Con el análisis al cierre, `contamination=0.1` fija que ~10 % de la **cohorte** quede marcada por el "
          f"modelo (≈ {round(0.1 * n_coh)} de {n_coh} sesiones), sean o no anómalas. Con "
          f"{100 * cfg['n_anomalas_test'] / n_coh:.0f} % de anómalas en la cohorte (prevalencia elegida para tener "
          "suficientes positivos, no realista), la mayoría de las marcas caen en sesiones anómalas: por eso la FRR del "
          "modelo es baja y su FAR alto. Con prevalencias realistas (5–10 %) las marcas se reparten distinto: ver "
          "`aporte_modelo.md`. AUC, AP y EER usan el score continuo y no dependen de ese umbral.")
        w("- En la sección de sensibilidad, la contaminación se agrega a la población, que ya forma parte de la cohorte "
          "junto con las sesiones de prueba.")
    else:
        w("- La FRR del Isolation Forest queda cerca de `contamination=0.1` **por construcción**: el umbral se fija "
          "para que ~10 % de la población de entrenamiento quede marcada. Es una tasa de revisión elegida por diseño, "
          "no una tasa de fraude estimada.")
    w("- Los perfiles `pegado_masivo`, `cambio_pestana` y `tecleo_automatizado` se construyeron alrededor de los "
      "umbrales de las reglas; que las reglas los detecten es una verificación de que se disparan cuando "
      "corresponde, no evidencia de desempeño frente a fraude real.")
    w("- El perfil informativo para el componente de IA es `ritmo_distinto` (ver barrido): sin señales discretas, "
      "la detección depende enteramente de cuán separada esté la sesión de la línea base poblacional.")
    w("- Con pocas sesiones por repetición las métricas tienen variabilidad apreciable; por eso se reportan "
      "desvíos e intervalos entre repeticiones y no solo el valor puntual.")
    w("- Validez externa pendiente: las anomalías sintéticas no representan necesariamente las conductas reales; "
      "el mismo script se puede reutilizar con métricas de sesiones del piloto reemplazando el generador.")
    (out / f"resultados_sinteticos{sufijo}.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repeticiones", type=int, default=20)
    ap.add_argument("--semilla", type=int, default=2026)
    ap.add_argument("--n-poblacion", type=int, default=40)
    ap.add_argument("--contaminacion", type=float, default=0.0)
    ap.add_argument("--n-normales", type=int, default=40)
    ap.add_argument("--n-anomalas", type=int, default=40)
    ap.add_argument("--dificultad", type=float, default=2.0)
    ap.add_argument("--barrido", default="0,0.5,1,1.5,2,3", help="niveles de dificultad separados por coma")
    ap.add_argument("--sin-barrido", action="store_true")
    ap.add_argument("--sensibilidad-contaminacion", type=float, default=0.1,
                    help="corre además una variante con población contaminada (0 = no correrla)")
    ap.add_argument("--protocolo", choices=PROTOCOLOS, default="poblacion_previa",
                    help="poblacion_previa (Incremento 6) o cierre (cohorte al cierre, Incremento 16)")
    ap.add_argument("--sufijo", default=None,
                    help="sufijo de los archivos de salida (por defecto: '' con poblacion_previa, '_inc16' con cierre)")
    ap.add_argument("--salida", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args(argv)
    suf = args.sufijo if args.sufijo is not None else ("_inc16" if args.protocolo == "cierre" else "")

    cfg = ExperimentConfig(
        repeticiones=args.repeticiones,
        semilla_base=args.semilla,
        n_poblacion=args.n_poblacion,
        contaminacion_poblacion=args.contaminacion,
        n_normales_test=args.n_normales,
        n_anomalas_test=args.n_anomalas,
        params=SyntheticParams(dificultad=args.dificultad),
        protocolo=args.protocolo,
    )
    out: Path = args.salida
    out.mkdir(parents=True, exist_ok=True)

    print(f"Corriendo {cfg.repeticiones} repeticiones…", flush=True)
    res = run_experiment(cfg)

    sweep = []
    if not args.sin_barrido:
        levels = [float(x) for x in args.barrido.split(",") if x.strip()]
        print(f"Barrido de dificultad: {levels}…", flush=True)
        sweep = run_sweep(cfg, levels)

    sens = None
    if args.sensibilidad_contaminacion > 0 and args.contaminacion == 0:
        print(f"Sensibilidad con contaminación {args.sensibilidad_contaminacion}…", flush=True)
        sens = run_experiment(replace(cfg, contaminacion_poblacion=args.sensibilidad_contaminacion))

    write_report(out, res, sweep, sens, suf)

    summary = {
        "config": res["config"],
        "versiones": {"scikit-learn": sklearn.__version__, "numpy": np.__version__},
        "agregado": res["agregado"],
        "por_repeticion": res["por_repeticion"],
        "barrido_dificultad": sweep,
        "sensibilidad_contaminacion": {"config": sens["config"], "agregado": sens["agregado"]} if sens else None,
    }
    (out / f"resultados_sinteticos{suf}.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    with open(out / f"sesiones_sinteticas{suf}.csv", "w", newline="", encoding="utf-8") as f:
        cols = ["rep", "idx", "perfil", "y_true", "marcada", "marcada_reglas", "marcada_modelo", "score_modelo", "indicadores"]
        wr = csv.DictWriter(f, fieldnames=cols)
        wr.writeheader()
        for r in res["registros"]:
            wr.writerow({**r, "indicadores": "|".join(r["indicadores"])})

    with open(out / f"roc_modelo{suf}.csv", "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["curva", "fpr_frr", "tpr", "far", "umbral"])
        for name, perfil in (("todas", None), ("ritmo_distinto", "ritmo_distinto")):
            for fpr, tpr, thr in pooled_roc(res["registros"], perfil):
                wr.writerow([name, f"{fpr:.4f}", f"{tpr:.4f}", f"{1 - tpr:.4f}", f"{thr:.4f}" if np.isfinite(thr) else "inf"])

    if sweep:
        with open(out / f"barrido_dificultad{suf}.csv", "w", newline="", encoding="utf-8") as f:
            wr = csv.DictWriter(f, fieldnames=list(sweep[0].keys()))
            wr.writeheader()
            wr.writerows(sweep)

    a = res["agregado"]
    print(f"Pipeline: FAR {a['pipeline']['far']['mean']:.3f}  FRR {a['pipeline']['frr']['mean']:.3f}")
    print(f"Modelo:   AUC {a['modelo_score']['auc_roc']['mean']:.3f}  EER {a['modelo_score']['eer']['mean']:.3f}  "
          f"AP {a['modelo_score']['average_precision']['mean']:.3f}")
    print(f"Reporte: {out / f'resultados_sinteticos{suf}.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
