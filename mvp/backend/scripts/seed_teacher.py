"""
Crea (o resetea la contraseña de) un usuario docente para poder loguearse
en el dashboard. Uso:

    python -m scripts.seed_teacher docente@uade.edu.ar 1234
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.auth import hash_password
from app.database import SessionLocal, engine
from app.db_migrations import upgrade_db
from app.models import User


def main(email: str, password: str) -> None:
    # Revisión del Incremento 16: antes se creaban las tablas con `create_all`; sobre una base
    # vacía eso dejaba el esquema de models.py SIN `alembic_version`, y el primer arranque del
    # backend la tomaba por una base anterior a P02 y fallaba al reaplicar la migración 0002
    # ("duplicate column retencion_dias"). Ahora se usa el mismo camino que el backend.
    upgrade_db(engine)
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if user:
            user.password_hash = hash_password(password)
            print(f"Contraseña actualizada para {email}")
        else:
            user = User(email=email, password_hash=hash_password(password))
            db.add(user)
            print(f"Docente creado: {email}")
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Uso: python -m scripts.seed_teacher <email> <password>")
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])
