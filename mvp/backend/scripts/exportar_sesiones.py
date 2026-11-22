"""
Exporta las sesiones de SIMULACIÓN etiquetadas a un CSV sin datos personales
(Fase 2, P03; protocolo en mvp/docs/simulaciones/protocolo.md).

Lee la base directamente (la etiqueta de condición no sale por la API del
docente). Usa la misma `DATABASE_URL` que el backend; la base tiene que estar
migrada (el backend lo hace al arrancar).

Una fila por sesión finalizada con condición declarada:
- alias de sesión, evaluación y participante (S001, E01, P01: no reversibles
  desde el CSV);
- condición y `y_true` (1 = condición distinta de `normal`);
- lo que el sistema marcó al finalizar: `marcada` (requiere revisión),
  `marcada_reglas`, `marcada_modelo` e `indicadores`;
- cantidad de eventos, duración y las métricas de sesión completa.

No exporta códigos de participante, fechas, contexto, consignas, eventos
crudos ni revisiones.

Uso (desde mvp/backend):

    python -m scripts.exportar_sesiones --salida simulaciones.csv
    python -m scripts.exportar_sesiones --evaluacion ABC123 --salida sim.csv
    DATABASE_URL=postgres://... python -m scripts.exportar_sesiones --salida sim.csv
"""
import argparse
import csv
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import models  # noqa: E402
from app.evaluation.reales import COLUMNAS_BASE, registros_desde_sesiones  # noqa: E402


def cargar_sesiones(db, codigos: Optional[list[str]] = None) -> list[dict]:
    """Sesiones finalizadas (opcionalmente de ciertas evaluaciones), ordenadas por inicio."""
    q = db.query(models.Session).filter(models.Session.status == models.SessionStatus.ended)
    if codigos:
        q = q.join(models.Exam).filter(models.Exam.join_code.in_([c.upper() for c in codigos]))
    salida = []
    for s in q.order_by(models.Session.started_at, models.Session.id).all():
        n_eventos = db.query(models.Event).filter(models.Event.session_id == s.id).count()
        dur = (s.ended_at - s.started_at).total_seconds() if s.ended_at and s.started_at else None
        salida.append({
            "exam_id": s.exam_id,
            "participant_id": s.participant_id,
            "condicion": s.condicion_simulacion,
            "needs_review": s.needs_review,
            "indicadores": [(i.kind, i.level.value) for i in s.indicators],
            "metricas": {m.name: m.value for m in s.metrics if m.item_ref is None},
            "n_eventos": n_eventos,
            "duracion_s": dur,
        })
    return salida


def escribir_csv(filas: list[dict], destino: Path) -> None:
    metricas = sorted({k for f in filas for k in f if k not in COLUMNAS_BASE})
    with open(destino, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNAS_BASE + metricas, restval="")
        w.writeheader()
        w.writerows(filas)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--evaluacion", action="append", help="código de la evaluación (se puede repetir); por defecto, todas")
    ap.add_argument("--salida", required=True, type=Path, help="archivo CSV de salida")
    ap.add_argument("--incluir-sin-etiqueta", action="store_true",
                    help="incluir también sesiones sin condición (condicion vacía; el análisis las ignora)")
    args = ap.parse_args(argv)

    from app.database import SessionLocal  # se importa acá para respetar DATABASE_URL del entorno

    db = SessionLocal()
    try:
        sesiones = cargar_sesiones(db, args.evaluacion)
    finally:
        db.close()
    filas = registros_desde_sesiones(sesiones, incluir_sin_etiqueta=args.incluir_sin_etiqueta)
    escribir_csv(filas, args.salida)
    etiquetadas = sum(1 for f in filas if f["condicion"])
    print(f"{len(filas)} sesiones exportadas ({etiquetadas} con condición) -> {args.salida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
