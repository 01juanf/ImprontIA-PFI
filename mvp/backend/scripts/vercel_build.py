"""
Paso de build del despliegue en Vercel (nov. 2026).

Vercel ejecuta la API como una función: cada arranque en frío vuelve a importar `app.main`.
Para no aplicar las migraciones ni crear los docentes de SEED_TEACHERS en cada arranque, en
Vercel se fija MIGRATE_ON_STARTUP=0 y este guion los aplica UNA vez por despliegue, durante el
build (lo invoca `buildCommand` en mvp/backend/vercel.json), con las mismas variables de
entorno que usará la función.

Uso local (equivalente):  DATABASE_URL=... JWT_SECRET=... python -m scripts.vercel_build

Se niega a correr sin DATABASE_URL: sin ella migraría una base SQLite del directorio de build,
que se descarta, y la función arrancaría contra una base vacía.
"""
import os
import sys


def main() -> int:
    if not os.environ.get("DATABASE_URL", "").strip():
        print(
            "ERROR: falta DATABASE_URL. Configurarla en Vercel (Settings → Environment Variables) "
            "con la URL de Neon antes de desplegar. Ver mvp/docs/despliegue_vercel.md.",
            file=sys.stderr,
        )
        return 1

    # Que el import de app.main no aplique nada por su cuenta: lo hace este guion, una vez.
    os.environ["MIGRATE_ON_STARTUP"] = "0"
    from app.database import engine
    from app.db_migrations import current_revision, upgrade_db

    # Primero el esquema: app.main purga las sesiones vencidas al importarse (RNF10) y para
    # eso las tablas tienen que existir (en el primer despliegue, la base de Neon está vacía).
    upgrade_db(engine)
    print(f"Migraciones aplicadas: la base está en la revisión {current_revision(engine)}.")

    from app.main import seed_teachers_from_env

    creados = seed_teachers_from_env()
    print(f"Docentes creados desde SEED_TEACHERS: {', '.join(creados) if creados else 'ninguno nuevo'}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
