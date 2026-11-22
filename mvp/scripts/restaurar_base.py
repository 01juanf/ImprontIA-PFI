"""
Restauración de un respaldo de ImprontIA (despliegue en la nube, 30/10/2026).

Carga en una base PostgreSQL un archivo hecho con scripts/respaldar_base.py. Sirve para:
- recuperar los datos si algo se rompió;
- mudar la base a otro proveedor (p. ej. de la Postgres free de Render, que vence, a una que no).

Uso (desde mvp/; la URL de la base DESTINO va en una variable de entorno):

    export DATABASE_URL='postgresql://usuario:clave@host/base?sslmode=require'
    python scripts/restaurar_base.py respaldos/improntia_2026-10-30_1530.dump --confirmar <nombre-de-la-base>

`--confirmar` tiene que repetir el nombre de la base destino (lo último de la URL, antes del `?`):
evita restaurar por error sobre la base equivocada.

Qué hace: borra las tablas de ImprontIA que ya existan en la base destino y las reemplaza por las
del respaldo, todo en una sola transacción (si algo falla, la base queda como estaba). Las demás
tablas de esa base no se tocan. Conviene apagar la API (Render: Suspend) mientras tanto y volver a
encenderla después; al arrancar, el backend aplica las migraciones que falten.

No imprime la clave (se pasa a pg_restore por PGPASSWORD). Requiere pg_restore de la misma versión
mayor que el respaldo o más nueva.
"""
import argparse
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
from respaldar_base import env_with_password, libpq_url_and_password, read_database_url, redact, require_tool  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("archivo", type=Path, help="archivo .dump hecho con respaldar_base.py")
    ap.add_argument("--confirmar", required=True, metavar="NOMBRE_BASE",
                    help="nombre de la base destino, para confirmar que se va a reemplazar su contenido")
    args = ap.parse_args(argv)

    if not args.archivo.is_file():
        sys.exit(f"No existe el archivo {args.archivo}.")
    url = read_database_url()
    try:
        libpq_url, password = libpq_url_and_password(url)
    except ValueError as e:
        sys.exit(str(e))
    base = urlsplit(libpq_url).path.lstrip("/")
    if args.confirmar != base:
        sys.exit(f"--confirmar no coincide con la base de DATABASE_URL ({base!r}). No se tocó nada.")
    pg_restore = require_tool("pg_restore")

    print(f"Respaldo: {args.archivo}")
    print(f"Destino:  {redact(url)}")
    r = subprocess.run(
        [pg_restore, "--clean", "--if-exists", "--no-owner", "--no-privileges", "--single-transaction",
         "--exit-on-error", f"--dbname={libpq_url}", str(args.archivo)],
        env=env_with_password(password), capture_output=True, text=True,
    )
    if r.returncode != 0:
        msg = r.stderr.strip()
        if password:
            msg = msg.replace(password, "***")
        print(f"\nFALLÓ pg_restore (la base quedó como estaba):\n{msg}", file=sys.stderr)
        return 1
    print("\nRESTAURACIÓN OK — reiniciar (o reanudar) la API y entrar al dashboard para comprobar los datos.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
