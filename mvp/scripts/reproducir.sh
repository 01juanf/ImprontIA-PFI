#!/usr/bin/env bash
# =============================================================================
# Paquete mínimo de reproducibilidad de ImprontIA (MVP).
#
# Punto de entrada único que, desde una copia limpia del repositorio:
#   (a) corre los tests del backend (pytest);
#   (b) corre los tests del dashboard (npm test) y compila el build de producción;
#   (c) corre la evaluación sintética del pipeline con el protocolo del MVP
#       (análisis de la cohorte al cierre): backend/scripts/evaluar.py --protocolo cierre
#       -> docs/evaluacion/resultados_sinteticos_inc16.{md,json} y CSV con sufijo _inc16;
#   (d) corre el aporte incremental del modelo sobre las reglas:
#       backend/scripts/aporte_modelo.py -> docs/evaluacion/aporte_modelo.{md,csv};
#   (e) opcionalmente, las mediciones de RNF (scripts/medir_rnf.py) y la evaluación
#       experta y automatizada de usabilidad (scripts/evaluar_usabilidad.py);
# y al final imprime el commit de git (`git rev-parse HEAD`) y escribe un manifiesto
# sha256 de los archivos de resultados producidos en esta corrida:
#   docs/evaluacion/MANIFIESTO.sha256   (verificable con `sha256sum -c`)
#
# Uso (desde mvp/, o desde cualquier carpeta: el script se ubica solo). Se invoca con bash,
# así funciona también desde el ZIP de GitHub aunque no conserve el permiso de ejecución:
#
#   bash scripts/reproducir.sh                 # (a)–(d), corrida completa (~10–15 min)
#   bash scripts/reproducir.sh --rapido        # (d) con 5 semillas, salida aparte (ver abajo)
#   bash scripts/reproducir.sh --rnf           # + RNF07/09/11 con SQLite (~10 min más)
#   bash scripts/reproducir.sh --usabilidad --axe /tmp/axe/node_modules/axe-core/axe.min.js
#   bash scripts/reproducir.sh --python backend/.venv/bin/python
#
# Opciones:
#   --python RUTA      intérprete con las dependencias del backend (requirements.txt).
#                      Por defecto: $PYTHON, backend/.venv/bin/python o python3.
#   --rapido           aporte del modelo con 5 semillas (en lugar de 30) y 2 de chequeo de
#                      orden; escribe en docs/evaluacion/rapido/ para NO pisar la corrida
#                      completa versionada. Sirve para verificar que todo corre.
#   --rnf              corre además scripts/medir_rnf.py --etiqueta sqlite y regenera
#                      docs/evaluacion/rnf_mediciones.md. Requiere Playwright + Chromium.
#   --usabilidad       corre además scripts/evaluar_usabilidad.py (requiere --axe o
#                      $AXE_CORE_JS, Playwright + Chromium). Usa los puertos 8100 y 5180.
#   --axe RUTA         ruta a axe-core/axe.min.js (instalarlo fuera del repo:
#                      mkdir -p /tmp/axe && (cd /tmp/axe && npm install axe-core@4.10.2)).
#   --evaluar-previo   corre además evaluar.py con el protocolo anterior (población previa,
#                      Incremento 6), que regenera docs/evaluacion/resultados_sinteticos.md.
#   --sin-tests        saltea (a) y (b) (solo resultados).
#   -h, --ayuda        muestra esta ayuda.
#
# Identificador de versión: la entrega final se etiqueta en git como `v1.0`. La versión de la app está en mvp/VERSION;
# el backend la informa en GET /health y GET /version junto con el commit (GIT_COMMIT), y el
# dashboard la muestra en el pie (VITE_GIT_COMMIT, fijado al compilar). Este script exporta
# GIT_COMMIT y VITE_GIT_COMMIT con el commit actual.
#
# Requisitos: bash, git, Node.js 20+ con npm, Python 3.12 con requirements.txt instalado
# (y httpx + playwright para --rnf/--usabilidad). Sale con código != 0 ante el primer error.
# =============================================================================
set -euo pipefail

MVP="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$MVP/backend"
DASHBOARD="$MVP/dashboard"
EVAL="$MVP/docs/evaluacion"

PY="${PYTHON:-}"
RAPIDO=0; RNF=0; USAB=0; PREVIO=0; TESTS=1
AXE="${AXE_CORE_JS:-}"

ayuda() { sed -n '3,/^# =====/p' "${BASH_SOURCE[0]}" | sed '$d; s/^# \{0,1\}//'; }

while [ $# -gt 0 ]; do
  case "$1" in
    --python) PY="$2"; shift 2 ;;
    --rapido) RAPIDO=1; shift ;;
    --rnf) RNF=1; shift ;;
    --usabilidad) USAB=1; shift ;;
    --axe) AXE="$2"; shift 2 ;;
    --evaluar-previo) PREVIO=1; shift ;;
    --sin-tests) TESTS=0; shift ;;
    -h|--ayuda|--help) ayuda; exit 0 ;;
    *) echo "Opción desconocida: $1 (ver --ayuda)" >&2; exit 2 ;;
  esac
done

if [ -z "$PY" ]; then
  if [ -x "$BACKEND/.venv/bin/python" ]; then PY="$BACKEND/.venv/bin/python"; else PY="python3"; fi
fi
# Ruta relativa -> absoluta (los pasos cambian de carpeta).
case "$PY" in
  */*) PY="$(cd "$(dirname "$PY")" && pwd)/$(basename "$PY")" ;;
esac
if [ "$USAB" = 1 ] && { [ -z "$AXE" ] || [ ! -f "$AXE" ]; }; then
  echo "--usabilidad requiere --axe RUTA/axe.min.js (o AXE_CORE_JS)" >&2; exit 2
fi

COMMIT="$(git -C "$MVP" rev-parse HEAD 2>/dev/null || echo desconocido)"
if [ "$COMMIT" != desconocido ] && [ -n "$(git -C "$MVP" status --porcelain 2>/dev/null)" ]; then
  SUCIO=" (con cambios sin commitear: los resultados NO corresponden exactamente a este commit)"
else
  SUCIO=""
fi
export GIT_COMMIT="$COMMIT" VITE_GIT_COMMIT="$COMMIT"
VERSION="$(head -n1 "$MVP/VERSION" 2>/dev/null || echo desconocida)"

paso() { printf '\n==> %s\n' "$*"; }

mkdir -p "$EVAL"
MARCA="$(mktemp)"
trap 'rm -f "$MARCA"' EXIT
sleep 1  # para que los archivos de esta corrida sean estrictamente más nuevos que la marca

echo "ImprontIA v$VERSION · commit $COMMIT$SUCIO"
echo "Python: $PY ($("$PY" --version 2>&1))"

if [ "$TESTS" = 1 ]; then
  paso "(a) Tests del backend (pytest)"
  (cd "$BACKEND" && "$PY" -m pytest -q -p no:cacheprovider)

  paso "(b) Tests del dashboard (npm test) y build de producción"
  if [ ! -d "$DASHBOARD/node_modules" ]; then (cd "$DASHBOARD" && npm ci); fi
  (cd "$DASHBOARD" && npm test && npm run build)
fi

paso "(c) Evaluación sintética, protocolo de cierre (evaluar.py --protocolo cierre)"
(cd "$BACKEND" && "$PY" -m scripts.evaluar --protocolo cierre --salida "$EVAL")
if [ "$PREVIO" = 1 ]; then
  paso "(c') Evaluación sintética, protocolo anterior (población previa)"
  (cd "$BACKEND" && "$PY" -m scripts.evaluar --salida "$EVAL")
fi

if [ "$RAPIDO" = 1 ]; then
  paso "(d) Aporte del modelo, modo rápido (5 semillas) -> docs/evaluacion/rapido/"
  mkdir -p "$EVAL/rapido"
  (cd "$BACKEND" && "$PY" -m scripts.aporte_modelo --semillas 5 --semillas-chequeo 2 --salida "$EVAL/rapido")
else
  paso "(d) Aporte del modelo (aporte_modelo.py, 30 semillas)"
  (cd "$BACKEND" && "$PY" -m scripts.aporte_modelo --salida "$EVAL")
fi

if [ "$RNF" = 1 ]; then
  paso "(e) Mediciones de RNF (medir_rnf.py, SQLite)"
  (cd "$MVP" && "$PY" scripts/medir_rnf.py --etiqueta sqlite --backend-python "$PY")
  # El informe combina todas las corridas disponibles (la de PostgreSQL, si está versionada).
  set -- "$EVAL/rnf_mediciones_sqlite.json"
  [ -f "$EVAL/rnf_mediciones_postgres.json" ] && set -- "$@" "$EVAL/rnf_mediciones_postgres.json"
  (cd "$MVP" && "$PY" scripts/medir_rnf.py --informe "$@")
fi

if [ "$USAB" = 1 ]; then
  paso "(e) Evaluación experta y automatizada de usabilidad (evaluar_usabilidad.py)"
  (cd "$MVP" && "$PY" scripts/evaluar_usabilidad.py --backend-python "$PY" --axe "$AXE")
fi

paso "Manifiesto sha256 de los resultados de esta corrida"
MANIFIESTO="$EVAL/MANIFIESTO.sha256"
{
  echo "# ImprontIA v$VERSION · commit $COMMIT$SUCIO"
  echo "# Generado por scripts/reproducir.sh el $(date -u '+%Y-%m-%d %H:%M UTC'). Verificar desde mvp/ con: sha256sum -c docs/evaluacion/MANIFIESTO.sha256"
  (cd "$MVP" && find docs/evaluacion -type f -newer "$MARCA" ! -name MANIFIESTO.sha256 | LC_ALL=C sort | while IFS= read -r f; do
    sha256sum "$f"
  done)
} > "$MANIFIESTO"
grep -v '^#' "$MANIFIESTO" || true

echo
echo "Listo. Commit: $COMMIT$SUCIO"
echo "Manifiesto: docs/evaluacion/MANIFIESTO.sha256 ($(grep -vc '^#' "$MANIFIESTO") archivos)"
