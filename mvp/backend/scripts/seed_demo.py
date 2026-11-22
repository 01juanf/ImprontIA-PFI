"""
Puebla una evaluación existente con sesiones SINTÉTICAS a través de la API
HTTP real (POST /sessions/start -> /events -> /end), para que la demo del
dashboard tenga una línea base poblacional (>= MIN_SESSIONS_FOR_MODEL) y el
indicador del Isolation Forest pueda aparecer.

Usa el mismo generador que la evaluación (app/evaluation/synthetic.py). Los
participantes se nombran SINT-### para que en el dashboard quede a la vista
que no son personas reales.

Uso (con el backend corriendo):

    python -m scripts.seed_demo --join-code A3F9C1 --normales 24 --atipicas 1
    python -m scripts.seed_demo --api http://127.0.0.1:8010 --join-code A3F9C1 --semilla 7
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402
import numpy as np  # noqa: E402

from app.evaluation.synthetic import SyntheticParams, generate_session  # noqa: E402

# Pausa entre el último evento y la entrega, y antes del primero (ms): una sesión real no
# termina en el mismo instante en que se suelta la última tecla.
MARGEN_MS = 2_000.0


def ajustar_duraciones(db_url: str, spans_ms: dict[str, float]) -> int:
    """
    Revisión del Incremento 16: las sesiones sintéticas se cargan en décimas de segundo, así
    que su duración real según el servidor (inicio a fin, `session_wall_duration_ms` del
    panorama) quedaba en ~0,1 s aunque sus eventos abarquen minutos. Se corre `started_at`
    hacia atrás para que la duración real sea la de sus eventos más un margen; `ended_at`
    (la entrega real) no cambia. Necesita acceso a la misma base que el backend.
    Devuelve cuántas sesiones se ajustaron.
    """
    from datetime import timedelta

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app import models
    from app.config import normalize_database_url

    engine = create_engine(normalize_database_url(db_url))
    db = sessionmaker(bind=engine)()
    n = 0
    try:
        for sid, span in spans_ms.items():
            s = db.get(models.Session, sid)
            if s is None or s.ended_at is None:
                continue
            s.started_at = s.ended_at - timedelta(milliseconds=span + 2 * MARGEN_MS)
            n += 1
        db.commit()
    finally:
        db.close()
        engine.dispose()
    return n


def _db_disponible(db_url: str) -> bool:
    if db_url.startswith("sqlite:///"):
        return Path(db_url[len("sqlite:///"):]).exists()  # no crear una base vacía por error
    return True


def run_session(client: httpx.Client, join_code: str, participant: str, events: list[dict], batch_size: int = 200) -> dict:
    r = client.post("/sessions/start", json={
        "exam_code": join_code,
        "participant_id": participant,
        "session_type": "exam",
        "context": {"origen": "sintetico"},
        "consent_given": True,
    })
    r.raise_for_status()
    s = r.json()
    headers = {"X-Session-Token": s["session_token"]}
    for seq, i in enumerate(range(0, len(events), batch_size), start=1):
        client.post(f"/sessions/{s['session_id']}/events", headers=headers,
                    json={"seq": seq, "events": events[i:i + batch_size]}).raise_for_status()
    end = client.post(f"/sessions/{s['session_id']}/end", headers=headers)
    end.raise_for_status()
    return {"session_id": s["session_id"], **end.json()}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--api", default="http://127.0.0.1:8010")
    ap.add_argument("--join-code", required=True)
    ap.add_argument("--normales", type=int, default=24)
    ap.add_argument("--atipicas", type=int, default=1, help="sesiones `ritmo_distinto` (solo detectables por el modelo)")
    ap.add_argument("--dificultad", type=float, default=3.0)
    ap.add_argument("--semilla", type=int, default=7)
    ap.add_argument("--database-url", default=None,
                    help="base del backend, para ajustar la duración real de las sesiones (default: DATABASE_URL)")
    ap.add_argument("--sin-ajustar-duracion", action="store_true",
                    help="no tocar la base: las sesiones quedan con la duración real de la carga (~0,1 s)")
    args = ap.parse_args(argv)

    rng = np.random.default_rng(args.semilla)
    params = SyntheticParams(dificultad=args.dificultad)
    flagged = 0
    spans: dict[str, float] = {}
    with httpx.Client(base_url=args.api, timeout=60) as client:
        for i in range(args.normales):
            events = generate_session(rng, params, "normal")
            res = run_session(client, args.join_code, f"SINT-{i + 1:03d}", events)
            spans[res["session_id"]] = max((e["t"] for e in events), default=0.0)
            flagged += int(res["needs_review"])
        for j in range(args.atipicas):
            events = generate_session(rng, params, "ritmo_distinto")
            res = run_session(client, args.join_code, f"SINT-ATIPICA-{j + 1:02d}", events)
            spans[res["session_id"]] = max((e["t"] for e in events), default=0.0)
            print(f"SINT-ATIPICA-{j + 1:02d}: session_id={res['session_id']} needs_review={res['needs_review']}")
    if not args.sin_ajustar_duracion:
        from app.config import database_url, normalize_database_url

        db_url = normalize_database_url(args.database_url) if args.database_url else database_url()
        if _db_disponible(db_url):
            n = ajustar_duraciones(db_url, spans)
            print(f"Duración real ajustada a la de los eventos en {n} sesiones.")
        else:
            print(f"Aviso: no se encontró la base {db_url}; las sesiones quedan con la duración de la carga.")
    print(f"{args.normales} sesiones normales sintéticas cargadas ({flagged} quedaron marcadas para revisión).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
