"""
Analiza las sesiones de SIMULACIÓN exportadas con `exportar_sesiones.py`
(Fase 2, P03; protocolo en mvp/docs/simulaciones/protocolo.md).

Calcula FAR, FRR, AUC-ROC, AP y EER con las mismas funciones que la
evaluación sintética (`app/evaluation/metrics.py`):

- Operación: lo que el sistema marcó al finalizar cada sesión, contra la condición.
- Modelo (fuera de línea): score del Isolation Forest de cada sesión, entrenado
  solo con sesiones `normal` y sin la sesión evaluada. Con
  `--excluir-participante`, además sin ninguna sesión de la misma persona.
- Intervalos 95 % remuestreando participantes.

Son resultados de simulaciones con pocas personas: exploratorios, no una
validación del sistema.

Uso (desde mvp/backend):

    python -m scripts.analizar_reales simulaciones.csv
    python -m scripts.analizar_reales simulaciones.csv --salida ../docs/simulaciones/resultados
    python -m scripts.analizar_reales simulaciones.csv --excluir-participante
"""
import argparse
import csv
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.evaluation.reales import analizar, fmt  # noqa: E402
from app.simulacion import CONDICIONES  # noqa: E402


def leer_csv(ruta: Path) -> list[dict]:
    with open(ruta, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _ic(res: dict, k: str, pct: bool) -> str:
    i = res["intervalos"].get(k)
    if not i or math.isnan(i["p2_5"]):
        return ""
    return f" [{fmt(i['p2_5'], pct)} – {fmt(i['p97_5'], pct)}]"


def reporte_md(res: dict, origen: str) -> str:
    g = res["global"]
    lineas = [
        "# Resultados de las simulaciones de examen",
        "",
        f"Generado: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} · origen: `{origen}` · "
        f"partición: {'por participante' if res['config']['excluir_participante'] else 'dejar una sesión afuera'}",
        "",
        "> Simulaciones rendidas por el equipo con condiciones declaradas: resultados **exploratorios**, "
        "no una validación del sistema ni del piloto (cap. 18).",
        "",
        f"Participantes: {res['participantes']} · sesiones: " + ", ".join(
            f"{c} {n}" for c, n in res["conteo_por_condicion"].items()),
        "",
    ]
    if g:
        op, mo = g["operacion"], g["modelo_score"]
        lineas += [
            "## Global",
            "",
            "| | Valor [IC 95 % por participantes] |",
            "|---|---|",
            f"| FAR (anomalías no detectadas, operación) | {fmt(op['far'], True)}{_ic(res, 'far', True)} |",
            f"| FRR (falsas alarmas, operación) | {fmt(op['frr'], True)}{_ic(res, 'frr', True)} |",
            f"| AUC-ROC del modelo | {fmt(mo['auc_roc'])}{_ic(res, 'auc_roc', False)} |",
            f"| AP del modelo | {fmt(mo['average_precision'])}{_ic(res, 'average_precision', False)} |",
            f"| EER del modelo | {fmt(mo['eer'])}{_ic(res, 'eer', False)} |",
            f"| Sesiones con score del modelo | {mo['n_con_score']} de {g['n']} |",
            "",
            "## Por condición (contra las sesiones normales)",
            "",
            "| Condición | n | Detectadas (operación / reglas / modelo) | FAR | AUC | AP | EER |",
            "|---|---|---|---|---|---|---|",
        ]
        for c, m in res["por_condicion"].items():
            lineas.append(
                f"| {c} | {m['n_anomalas']} | {m['detectadas_operacion']} / {m['detectadas_reglas']} / "
                f"{m['detectadas_modelo']} | {fmt(m['operacion']['far'], True)} | "
                f"{fmt(m['modelo_score']['auc_roc'])} | {fmt(m['modelo_score']['average_precision'])} | "
                f"{fmt(m['modelo_score']['eer'])} |")
        lineas.append("")
    if res["avisos"]:
        lineas += ["## Avisos", ""] + [f"- {a}" for a in res["avisos"]] + [""]
    return "\n".join(lineas)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv", type=Path, help="CSV de exportar_sesiones.py")
    ap.add_argument("--excluir-participante", action="store_true",
                    help="entrenar el modelo sin ninguna sesión de la misma persona")
    ap.add_argument("--bootstrap", type=int, default=1000, help="remuestreos de participantes (0 = sin intervalos)")
    ap.add_argument("--semilla", type=int, default=2026)
    ap.add_argument("--salida", type=Path, help="directorio para resultados_simulaciones.md/.json")
    args = ap.parse_args(argv)

    filas = leer_csv(args.csv)
    desconocidas = sorted({f["condicion"] for f in filas if f["condicion"] and f["condicion"] not in CONDICIONES})
    if desconocidas:
        print(f"Aviso: condiciones desconocidas ignoradas: {', '.join(desconocidas)}", file=sys.stderr)
    res = analizar(filas, excluir_participante=args.excluir_participante, n_boot=args.bootstrap, semilla=args.semilla)
    md = reporte_md(res, args.csv.name)
    print(md)
    if args.salida:
        args.salida.mkdir(parents=True, exist_ok=True)
        (args.salida / "resultados_simulaciones.md").write_text(md, encoding="utf-8")
        (args.salida / "resultados_simulaciones.json").write_text(
            json.dumps(res, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
