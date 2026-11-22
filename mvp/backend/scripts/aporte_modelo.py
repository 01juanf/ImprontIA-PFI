"""
Aporte incremental del modelo poblacional (Isolation Forest) sobre las reglas
determinísticas, con DATOS SINTÉTICOS y el protocolo de cohorte al cierre
(Incremento 16).

Pregunta: ¿qué sesiones detecta el modelo que las reglas no detectan, y a qué
costo en falsas alarmas? Se usa el código real del MVP, sin reimplementar nada:

- eventos sintéticos: app.evaluation.synthetic.generate_session (mismos
  parámetros por defecto que scripts/evaluar.py);
- métricas: app.processing.features.compute_all_features;
- reglas: app.processing.indicators.generate_indicators (sin reglas de examen,
  como en el protocolo de simulaciones);
- modelo: app.processing.cohort.analizar_cohorte, UNA vez sobre la cohorte
  completa, con las métricas continuas que le pasa routers/exams.py al cierre;
  la marca sale de indicators.indicator_from_anomaly.

Diseño por semilla y tamaño de cohorte N:
- cohorte por condición: N sesiones, de las cuales `prevalencia` (10 %) son de
  la condición y el resto normales;
- cohorte mixta: N sesiones con `prevalencia_mixta` (5 %) de cada una de las
  cuatro condiciones (20 % de no normales en total);
- sensibilidad: `suplantacion` con dificultad 1σ (por defecto 2σ).

Correspondencia condición (app/simulacion.py) -> perfil sintético
(app/evaluation/synthetic.py): pegado -> pegado_masivo, consulta_externa ->
cambio_pestana, transcripcion -> tecleo_automatizado, suplantacion ->
ritmo_distinto. Es una analogía: los perfiles no se construyeron a partir de
las conductas humanas de cada condición.

Chequeo de orden: se verifica que analizar_cohorte dé marcas idénticas al
permutar el orden de inserción de las sesiones, y se mide además cuánto cambian
las marcas si se reasignan los identificadores (el modelo ordena por id, que es
un UUID aleatorio: el resultado no depende del orden de llegada, pero sí del
orden arbitrario de los ids a través del submuestreo del Isolation Forest).

Uso (desde mvp/backend):

    python -m scripts.aporte_modelo                     # 30 semillas, N = 40 y 100
    python -m scripts.aporte_modelo --semillas 10 --tamanos 40
"""
import argparse
import csv
import sys
import time
from multiprocessing import Pool
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import sklearn  # noqa: E402
from scipy import stats  # noqa: E402

from app.evaluation.synthetic import SyntheticParams, generate_session  # noqa: E402
from app.processing.anomaly import CONTINUOUS_METRICS, MIN_SESSIONS_FOR_MODEL  # noqa: E402
from app.processing.cohort import analizar_cohorte  # noqa: E402
from app.processing.features import compute_all_features  # noqa: E402
from app.processing.indicators import THRESHOLDS, generate_indicators, indicator_from_anomaly  # noqa: E402

DEFAULT_OUT = Path(__file__).resolve().parent.parent.parent / "docs" / "evaluacion"

CONDICION_A_PERFIL = {
    "pegado": "pegado_masivo",
    "transcripcion": "tecleo_automatizado",
    "consulta_externa": "cambio_pestana",
    "suplantacion": "ritmo_distinto",
}
CONDICIONES = list(CONDICION_A_PERFIL)


def _ids(rng: np.random.Generator, n: int) -> list[str]:
    # Identificadores tipo UUID (aleatorios, como gen_uuid en models.py).
    return [f"{int(v):032x}" for v in rng.integers(0, 2**63, size=n)]


def _marcas_modelo(metrics: dict[str, dict[str, float]]) -> dict[str, bool]:
    res = analizar_cohorte(metrics)
    return {sid: (r is not None and indicator_from_anomaly(r) is not None) for sid, r in res.items()}, res


def run_cohort(rng: np.random.Generator, n: int, etiquetas: list[str], params: SyntheticParams,
               chequear_orden: bool = True) -> dict:
    """Genera la cohorte, aplica reglas por sesión y el modelo una vez al cierre."""
    rng.shuffle(etiquetas)
    ids = _ids(rng, n)
    feats, cont, reglas = {}, {}, {}
    for sid, cond in zip(ids, etiquetas):
        perfil = "normal" if cond == "normal" else CONDICION_A_PERFIL[cond]
        f = compute_all_features(generate_session(rng, params, perfil))
        feats[sid] = f
        cont[sid] = {k: f[k] for k in CONTINUOUS_METRICS if k in f}  # lo que lee routers/exams.py
        reglas[sid] = any(d.prioritizes_review for d in generate_indicators(f))
    modelo, res = _marcas_modelo(cont)

    z_max = [max(abs(t["z_score"]) for t in res[s].top_features) for s in ids if modelo[s]]
    base = {"ids": ids, "cond": dict(zip(ids, etiquetas)), "reglas": reglas, "modelo": modelo, "z_max_marcadas": z_max,
            "orden_identico": None, "acuerdo_reasignar_ids": None}
    if not chequear_orden:
        return base

    # Chequeo 1: permutar el orden de inserción (mismos ids) -> marcas idénticas.
    perm = list(ids)
    rng.shuffle(perm)
    modelo_perm, res_perm = _marcas_modelo({sid: cont[sid] for sid in perm})
    identico = modelo_perm == modelo and all(
        (res[s] is None and res_perm[s] is None) or res[s].anomaly_score == res_perm[s].anomaly_score for s in ids
    )
    # Chequeo 2: reasignar ids (otra permutación de filas para el Isolation Forest).
    nuevos = _ids(rng, n)
    mapa = dict(zip(ids, nuevos))
    modelo_relab, _ = _marcas_modelo({mapa[s]: cont[s] for s in ids})
    acuerdo_relab = float(np.mean([modelo[s] == modelo_relab[mapa[s]] for s in ids]))

    return {**base, "orden_identico": identico, "acuerdo_reasignar_ids": acuerdo_relab}


def metricas(c: dict, condicion: str) -> dict:
    ids = c["ids"]
    pos = [s for s in ids if c["cond"][s] == condicion]
    neg = [s for s in ids if c["cond"][s] == "normal"]
    R, M = c["reglas"], c["modelo"]

    def rate(sub, f):
        return float(np.mean([f(s) for s in sub])) if sub else float("nan")

    return {
        "n_pos": len(pos), "n_normales": len(neg),
        "recall_reglas": rate(pos, lambda s: R[s]),
        "recall_modelo": rate(pos, lambda s: M[s]),
        "recall_union": rate(pos, lambda s: R[s] or M[s]),
        "recall_incremental": rate(pos, lambda s: M[s] and not R[s]),
        "fpr_reglas": rate(neg, lambda s: R[s]),
        "fpr_modelo": rate(neg, lambda s: M[s]),
        "fpr_union": rate(neg, lambda s: R[s] or M[s]),
        "fpr_incremental": rate(neg, lambda s: M[s] and not R[s]),
    }


def ci(vals: list[float]) -> tuple[float, float, float]:
    v = np.asarray([x for x in vals if not np.isnan(x)], dtype=float)
    m = float(v.mean())
    if len(v) < 2 or v.std(ddof=1) == 0:
        return m, m, m
    h = float(stats.t.ppf(0.975, len(v) - 1) * v.std(ddof=1) / np.sqrt(len(v)))
    return m, max(0.0, m - h), min(1.0, m + h)


METRICAS = ["recall_reglas", "recall_modelo", "recall_union", "recall_incremental",
            "fpr_reglas", "fpr_modelo", "fpr_union", "fpr_incremental"]


def _tarea(t) -> tuple[list[dict], dict]:
    n, ei, esc, cond, params, semilla, chequear, prev, prev_mixta = t
    rng = np.random.default_rng([semilla, n, ei])
    if cond is None:
        k = int(round(n * prev_mixta))
        etiquetas = [c for c in CONDICIONES for _ in range(k)]
        conds_eval = CONDICIONES
    else:
        etiquetas = [cond] * int(round(n * prev))
        conds_eval = [cond]
    etiquetas += ["normal"] * (n - len(etiquetas))
    c = run_cohort(rng, n, etiquetas, params, chequear_orden=chequear)
    filas = [{"escenario": esc, "dificultad": params.dificultad, "n_cohorte": n, "semilla": semilla,
              "condicion": ce, **metricas(c, ce)} for ce in conds_eval]
    return filas, {k: c[k] for k in ("z_max_marcadas", "orden_identico", "acuerdo_reasignar_ids")}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--semillas", type=int, default=30)
    ap.add_argument("--semilla-base", type=int, default=2026)
    ap.add_argument("--tamanos", default="40,100")
    ap.add_argument("--prevalencia", type=float, default=0.10)
    ap.add_argument("--prevalencia-mixta", type=float, default=0.05)
    ap.add_argument("--dificultad-sensibilidad", type=float, default=1.0)
    ap.add_argument("--semillas-chequeo", type=int, default=5,
                    help="semillas (por escenario y N) en las que se corre el chequeo de orden")
    ap.add_argument("--procesos", type=int, default=2)
    ap.add_argument("--salida", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args(argv)
    tamanos = [int(x) for x in args.tamanos.split(",")]
    base_params = SyntheticParams()
    sens_params = SyntheticParams(dificultad=args.dificultad_sensibilidad)

    t0 = time.time()
    filas = []  # una por (escenario, N, semilla, condición)
    chequeos = {"cohortes": 0, "orden_identico": 0, "acuerdo": [], "z_max": []}

    escenarios = [(f"por_condicion", c, base_params) for c in CONDICIONES]
    escenarios.append(("mixta", None, base_params))
    escenarios.append((f"por_condicion_dif{args.dificultad_sensibilidad:g}", "suplantacion", sens_params))

    tareas = [(n, ei, esc, cond, params, args.semilla_base + s, s < args.semillas_chequeo,
               args.prevalencia, args.prevalencia_mixta)
              for n in tamanos for ei, (esc, cond, params) in enumerate(escenarios) for s in range(args.semillas)]
    with Pool(args.procesos) as pool:
        for i, (nuevas, ch) in enumerate(pool.imap(_tarea, tareas, chunksize=4)):
            filas.extend(nuevas)
            chequeos["z_max"].extend(ch["z_max_marcadas"])
            if ch["orden_identico"] is not None:
                chequeos["cohortes"] += 1
                chequeos["orden_identico"] += int(ch["orden_identico"])
                chequeos["acuerdo"].append(ch["acuerdo_reasignar_ids"])
            if (i + 1) % 30 == 0:
                print(f"{i + 1}/{len(tareas)} cohortes ({time.time() - t0:.0f} s)", flush=True)

    out: Path = args.salida
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "aporte_modelo.csv", "w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=list(filas[0].keys()))
        wr.writeheader()
        for r in filas:
            wr.writerow({k: (f"{v:.4f}" if isinstance(v, float) else v) for k, v in r.items()})

    # Agregado
    grupos = {}
    for r in filas:
        grupos.setdefault((r["escenario"], r["n_cohorte"], r["condicion"]), []).append(r)

    def pct(t):
        m, lo, hi = t
        return f"{100 * m:.1f} [{100 * lo:.1f}–{100 * hi:.1f}]"

    L = []
    w = L.append
    w("# Aporte del modelo poblacional sobre las reglas (datos sintéticos)")
    w("")
    w(f"_Generado por `scripts/aporte_modelo.py` el {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} "
      f"(scikit-learn {sklearn.__version__}, numpy {np.__version__}), {args.semillas} semillas "
      f"({args.semilla_base}…{args.semilla_base + args.semillas - 1}), {time.time() - t0:.0f} s. "
      "No editar las tablas a mano: regenerar con el script. Datos por semilla en `aporte_modelo.csv`._")
    w("")
    w("> **Advertencia.** Sesiones **sintéticas**, con parámetros no calibrados con personas. Los números muestran "
      "cómo se reparten las detecciones entre reglas y modelo para anomalías de forma conocida; **no** estiman el "
      "desempeño con estudiantes ni están validados con personas.")
    w("")
    w("## Método")
    w("")
    w("- Protocolo de **cohorte al cierre** (Incremento 16): por semilla se genera una cohorte de N sesiones, se "
      "calculan las métricas con `features.compute_all_features`, las reglas con `indicators.generate_indicators` "
      "(sin reglas de examen) y el modelo con **una** llamada a `cohort.analizar_cohorte` sobre todas las sesiones "
      f"(métricas continuas, Isolation Forest `contamination=0.1`, mínimo {MIN_SESSIONS_FOR_MODEL} sesiones). "
      "La marca del modelo es `indicator_from_anomaly`. Lo que ve el docente (\"requiere revisión\") es reglas ∨ modelo.")
    w(f"- Cohortes de N = {', '.join(map(str, tamanos))}. **Por condición**: {100 * args.prevalencia:.0f} % de la "
      "cohorte es de esa condición y el resto normal. **Mixta**: "
      f"{100 * args.prevalencia_mixta:.0f} % de cada condición ({100 * 4 * args.prevalencia_mixta:.0f} % no normal en total).")
    w("- Correspondencia condición → perfil sintético del Incremento 6: `pegado` → `pegado_masivo`, "
      "`transcripcion` → `tecleo_automatizado`, `consulta_externa` → `cambio_pestana`, `suplantacion` → "
      f"`ritmo_distinto` (dificultad {base_params.dificultad:g}σ; sensibilidad con {args.dificultad_sensibilidad:g}σ). "
      "Los tres primeros perfiles se construyeron alrededor de los umbrales de las reglas "
      f"({THRESHOLDS}); `transcripcion` como tecleo casi constante es el caso más favorable a la regla y una "
      "transcripción humana real probablemente no lo sea.")
    w("- Recall = proporción de sesiones de la condición marcadas; FPR = proporción de sesiones normales de la misma "
      "cohorte marcadas. **Recall incremental** = marcadas por el modelo y no por las reglas. **FPR incremental** = "
      "normales marcadas solo por el modelo. Cada celda: media entre semillas, en %, con IC 95 % (t de Student) "
      "entre semillas. La detección es transductiva: las sesiones anómalas también forman parte de la población "
      "con la que se ajusta el modelo, como en un examen real.")
    w("")

    def tabla(esc, titulo):
        w(f"## {titulo}")
        w("")
        w("| Condición | N | Recall reglas | Recall modelo | Recall reglas ∨ modelo | **Recall incremental** | FPR reglas | FPR modelo | FPR reglas ∨ modelo |")
        w("|---|---|---|---|---|---|---|---|---|")
        for cond in CONDICIONES:
            for n in tamanos:
                g = grupos.get((esc, n, cond))
                if not g:
                    continue
                v = {m: ci([r[m] for r in g]) for m in METRICAS}
                w(f"| `{cond}` | {n} | {pct(v['recall_reglas'])} | {pct(v['recall_modelo'])} | {pct(v['recall_union'])} "
                  f"| **{pct(v['recall_incremental'])}** | {pct(v['fpr_reglas'])} | {pct(v['fpr_modelo'])} | {pct(v['fpr_union'])} |")
        w("")

    tabla("por_condicion", f"Resultados por condición (cohorte con {100 * args.prevalencia:.0f} % de la condición)")
    tabla("mixta", f"Cohorte mixta ({100 * args.prevalencia_mixta:.0f} % de cada condición)")
    tabla(f"por_condicion_dif{args.dificultad_sensibilidad:g}",
          f"Sensibilidad: `suplantacion` con dificultad {args.dificultad_sensibilidad:g}σ")

    acuerdo = np.asarray(chequeos["acuerdo"])
    z = np.asarray(chequeos["z_max"])
    w("## Dependencia del orden")
    w("")
    w(f"- Permutar el orden en que se entregan las sesiones a `analizar_cohorte` (mismos identificadores): marcas y "
      f"scores **idénticos en {chequeos['orden_identico']} de {chequeos['cohortes']} cohortes** (chequeo corrido en las primeras "
      f"{args.semillas_chequeo} semillas de cada escenario y N). El resultado no depende del orden de llegada.")
    w(f"- Reasignar los identificadores (el modelo ordena por id, un UUID aleatorio, y el Isolation Forest submuestrea "
      f"por posición con `random_state=0`): la marca del modelo coincide en el {100 * acuerdo.mean():.1f} % de las "
      f"sesiones en promedio (mínimo por cohorte {100 * acuerdo.min():.1f} %). "
      + ("Las marcas tampoco cambian con otra asignación de identificadores." if acuerdo.min() == 1.0 else
         "El resultado es reproducible para una cohorte dada, pero algunas sesiones cerca de la frontera cambian de "
         "marca con otra asignación de identificadores; eso no es una propiedad del orden de entrega."))
    w("")
    w("## Los z-scores no explican la decisión del modelo")
    w("")
    if len(z):
        w(f"Junto a cada marca del modelo se listan las dos métricas con mayor |z| respecto de la cohorte "
          f"(`anomaly._top_deviating_features`). Son desvíos descriptivos univariados, calculados aparte del Isolation "
          f"Forest: no dicen qué divisiones aislaron a la sesión. En estas cohortes, de {len(z)} marcas del modelo, "
          f"el {100 * np.mean(z < 2):.1f} % tiene su mayor |z| por debajo de 2 y el {100 * np.mean(z < 1.5):.1f} % "
          "por debajo de 1,5 (una parte de las marcas no tiene ninguna métrica individual extrema). Deben "
          "presentarse como \"en qué métricas se aleja más de la cohorte\", no como el motivo de la marca.")
    w("")
    w("## Interpretación")
    w("")
    for cond in CONDICIONES:
        partes = []
        for n in tamanos:
            g = grupos.get(("por_condicion", n, cond))
            m_inc = ci([r["recall_incremental"] for r in g])
            m_r = ci([r["recall_reglas"] for r in g])
            partes.append(f"N = {n}: reglas {100 * m_r[0]:.1f} %, incremental del modelo {100 * m_inc[0]:.1f} %")
        incs = [ci([r["recall_incremental"] for r in grupos[("por_condicion", n, cond)]])[0] for n in tamanos]
        if max(incs) == 0:
            veredicto = "el modelo **no agrega ninguna detección**: todo lo que marca ya lo marcaban las reglas"
        elif max(incs) < 0.05:
            veredicto = "el aporte del modelo es marginal"
        else:
            veredicto = "las detecciones de esta condición vienen del modelo"
        w(f"- `{cond}`: {veredicto} ({'; '.join(partes)}).")
    fpr = {n: ci([r["fpr_incremental"] for k, g in grupos.items() if k[0] == "por_condicion" and k[1] == n for r in g])
           for n in tamanos}
    w("- Costo: en sesiones normales las reglas casi no disparan con estos parámetros, así que prácticamente todas las "
      "falsas alarmas del pipeline las agrega el modelo (FPR incremental medio, condiciones juntas: "
      + "; ".join(f"N = {n}: {100 * v[0]:.1f} %" for n, v in fpr.items())
      + "). Es la tasa de revisión fijada por `contamination=0.1` repartida entre normales y anómalas de la cohorte, "
      "no una tasa de fraude.")
    w("")
    w("## Limitaciones")
    w("")
    w("- Datos sintéticos, no validados con personas. Los perfiles de `pegado`, `consulta_externa` y `transcripcion` "
      "se definieron alrededor de los umbrales de las reglas, así que el 100 % de las reglas y el aporte nulo del modelo "
      "en esas condiciones son en buena parte consecuencia del diseño del generador. El aporte del modelo en "
      "`suplantacion` depende de cuánto se separe el ritmo de la persona de la cohorte (ver sensibilidad y "
      "`barrido_dificultad.csv`); con personas reales esa separación es desconocida.")
    w("- La correspondencia condición → perfil es una analogía. En particular, una transcripción humana no produce un "
      "tecleo casi constante; en esa condición el resultado real puede ser muy distinto.")
    w("- Con N = 40 y 10 % de prevalencia hay 4 sesiones de la condición por cohorte: el recall por cohorte toma "
      "pocos valores y los intervalos entre semillas son anchos.")
    w("- El modelo no ve las métricas discretas (pegado, pestañas): por diseño solo complementa a las reglas en la "
      "dinámica continua de teclado y mouse.")
    w("")
    (out / "aporte_modelo.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"Listo en {time.time() - t0:.0f} s -> {out / 'aporte_modelo.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
