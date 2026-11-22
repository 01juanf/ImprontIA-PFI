"""
Purga las sesiones cuyo plazo de conservación venció (RNF10, Incremento 16).

Uso (desde mvp/backend), con la misma DATABASE_URL que el backend:

    python -m scripts.purgar_vencidas

Pensado para ejecutarse como tarea periódica (cron del servidor o del servicio de
despliegue). El backend también la ejecuta al arrancar.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main() -> int:
    from app.database import SessionLocal
    from app.db_migrations import upgrade_db
    from app.database import engine
    from app.retention import purge_expired

    upgrade_db(engine)
    db = SessionLocal()
    try:
        n = purge_expired(db)
    finally:
        db.close()
    print(f"{n} sesión(es) eliminada(s) por vencimiento del plazo de conservación")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
