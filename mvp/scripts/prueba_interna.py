"""
Prueba interna end-to-end (T18, Incremento 9; ver mvp/docs/bitacora.md y la
decisión D03: no hay piloto con voluntarios, se reemplaza por evaluación
sintética + prueba interna).

Qué hace
--------
Levanta el sistema REAL (backend FastAPI + dashboard React compilado, base
SQLite temporal) y, con un navegador (Playwright/Chromium), ejecuta
escenarios guionados del lado del estudiante a través de la vista de examen
del dashboard (`/exam/<código>`): la captura la hace `capture.ts` dentro de la
página, los eventos viajan por la API como en uso real, las reglas corren en
`POST /sessions/{id}/end` (que recibe la respuesta entregada) y, desde el
Incremento 16, el modelo poblacional corre una sola vez al cerrar la evaluación
(`POST /exams/{id}/cerrar`), que el script invoca después de la entrega.
Después verifica, del lado docente:

1. qué indicadores generó el backend para cada sesión (API) y si coinciden
   con lo esperado para el escenario;
2. que la vista de detalle del dashboard muestre la misma cantidad de
   indicadores y el mismo estado "Requiere revisión / Sin indicadores";
3. que ningún evento guardado en la base contenga texto de la respuesta ni
   del portapapeles, ni identifique qué tecla se pulsó (RNF01: solo metadatos
   de tiempo);
4. que la respuesta entregada quede guardada con la sesión (Incremento 16) y
   que la sesión quede procesada.

Escenarios (cada uno en una evaluación NUEVA, con la misma línea base):
- `normal`: mouse + tecleo con ritmo variable + una salida breve de la pestaña.
- `pegado_masivo`: poco tecleo y un bloque de ~450 caracteres pegado.
- `cambios_foco`: tecleo normal con 7 salidas breves de la pestaña.
- `transcripcion`: tecleo a ritmo constante (duración de pulsación fija),
  como el de un texto transcripto o inyectado.

Línea base poblacional: antes de cada escenario se cargan `--normales`
sesiones SINTÉTICAS normales por la API real (scripts/seed_demo.py, semilla
fija) para que el Isolation Forest tenga población (>= 20). Por eso la
columna del modelo compara sesiones de navegador contra una línea base
sintética: valida que el componente funciona dentro del flujo, no mide su
desempeño.

Limitación conocida: Playwright fija la página como visible (emula el foco),
así que un cambio de pestaña real no dispara `visibilitychange` ni siquiera
con navegador visible. El escenario lo simula sobrescribiendo
`document.visibilityState` y despachando el evento nativo; el listener de
`capture.ts` que lo registra es el real. La prueba manual
(docs/evaluacion/protocolo_prueba_manual.md) cubre el cambio de pestaña real.

Salidas: `docs/evaluacion/prueba_interna.csv` (una fila por sesión),
`prueba_interna.json` (detalle completo) y `prueba_interna_resultados.md`
(tablas generadas); con `--sufijo _inc16` los nombres llevan ese sufijo y no
se pisan corridas anteriores. Opcionalmente, capturas del detalle docente por
escenario (`--capturas DIR`, las PNG no se versionan).

Requisitos: los mismos que scripts/capturas_demo.py (backend instalado,
`npm install` en dashboard/, Playwright para Python con Chromium).

Uso (desde mvp/):

    python scripts/prueba_interna.py --backend-python backend/.venv/bin/python
    python scripts/prueba_interna.py --repeticiones 1 --escenarios normal pegado_masivo
"""
import argparse
import csv
import json
import math
import os
import platform
import random
import re
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from capturas_demo import ANSWER, EMAIL, PASSWORD, PASTED, human_type, resolve_python, wait_http  # noqa: E402

MVP = Path(__file__).resolve().parent.parent
BACKEND = MVP / "backend"
DASHBOARD = MVP / "dashboard"
OUT_DEFAULT = MVP / "docs" / "evaluacion"

ESCENARIOS = ["normal", "pegado_masivo", "cambios_foco", "transcripcion"]

# Indicadores de REGLA esperados por escenario (backend: app/processing/indicators.py).
# El indicador del modelo poblacional se reporta aparte: depende de la línea base
# y no es parte de la expectativa de cada guion.
ESPERADOS = {
    "normal": set(),
    "pegado_masivo": {"paste_volume_alto"},
    "cambios_foco": {"cambios_pestana_frecuentes"},
    "transcripcion": {"ritmo_tecleo_atipico"},
}
REGLAS = ["paste_volume_alto", "cambios_pestana_frecuentes", "perdida_foco_prolongada", "ritmo_tecleo_atipico"]
MODELO = "atipico_modelo_poblacional"

DESCRIPCION = {
    "normal": "Mouse + tecleo con ritmo variable (pulsación 60–130 ms, entre teclas 70–220 ms) + 1 salida de pestaña de ~2 s.",
    "pegado_masivo": "Tecleo de una frase corta y pegado de un bloque de ~450 caracteres.",
    "cambios_foco": "Tecleo con ritmo variable intercalado con 7 salidas de pestaña de 1,5–3 s (simuladas, ver limitación).",
    "transcripcion": "Tecleo a ritmo constante: pulsación fija de 80 ms y 110 ms entre teclas.",
}

INTRO = "Una clave primaria identifica cada fila. "

# Claves que puede traer un evento además de t/type (capture.ts). Cualquier otra = posible fuga.
# Desde el Incremento 9 los eventos de teclado no llevan `code` (qué tecla): también se verifica.
# Desde el Incremento 16 `keyup` lleva `dwell` (duración calculada en el navegador, un número).
PAYLOAD_KEYS = {"x", "y", "state", "chars", "button", "scrollX", "scrollY", "dwell"}


# ---------------------------------------------------------------- acciones del estudiante

def human_mouse(page: Page, rng: random.Random, n_moves: int, w: int = 1280, h: int = 800) -> None:
    """Movimientos con velocidad ~N(0,6; 0,18) px/ms y 100–400 ms entre muestras (como el generador sintético)."""
    x, y = rng.uniform(200, w - 200), rng.uniform(150, h - 150)
    page.mouse.move(x, y)
    for _ in range(n_moves):
        dt = rng.uniform(100, 400)
        speed = max(0.05, rng.gauss(0.6, 0.18))
        ang = rng.uniform(0, 2 * math.pi)
        nx, ny = x + speed * dt * math.cos(ang), y + speed * dt * math.sin(ang)
        if not (10 < nx < w - 10):
            nx = x - speed * dt * math.cos(ang)
        if not (10 < ny < h - 10):
            ny = y - speed * dt * math.sin(ang)
        page.wait_for_timeout(dt)
        x, y = min(max(nx, 10), w - 10), min(max(ny, 10), h - 10)
        page.mouse.move(x, y)


def steady_type(page: Page, text: str, dwell_ms: float = 80, flight_ms: float = 110) -> None:
    for ch in text:
        key = "Space" if ch == " " else ch
        page.keyboard.down(key)
        page.wait_for_timeout(dwell_ms)
        page.keyboard.up(key)
        page.wait_for_timeout(flight_ms)


SIMULAR_SALIDA_JS = """(ms) => new Promise((resolve) => {
    const set = (state) => {
        Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => state });
        Object.defineProperty(document, 'hidden', { configurable: true, get: () => state === 'hidden' });
    };
    set('hidden');
    window.dispatchEvent(new Event('blur'));
    document.dispatchEvent(new Event('visibilitychange'));
    setTimeout(() => {
        set('visible');
        document.dispatchEvent(new Event('visibilitychange'));
        window.dispatchEvent(new Event('focus'));
        resolve();
    }, ms);
})"""


def tab_out(page: Page, ms: float) -> None:
    page.evaluate(SIMULAR_SALIDA_JS, ms)


def paste_block(page: Page, text: str) -> None:
    """Dispara el `paste` real del DOM (capture.ts registra solo la longitud) e inserta el texto sin teclado."""
    page.evaluate(
        """(text) => {
            const ta = document.querySelector('textarea');
            const dt = new DataTransfer();
            dt.setData('text', text);
            ta.dispatchEvent(new ClipboardEvent('paste', { clipboardData: dt, bubbles: true }));
        }""",
        text,
    )
    page.keyboard.insert_text(text)


def run_scenario_actions(page: Page, escenario: str, rng: random.Random) -> None:
    human_mouse(page, rng, 20)
    page.click("textarea")
    if escenario == "normal":
        mitad = len(ANSWER) // 2
        human_type(page, ANSWER[:mitad], rng)
        tab_out(page, rng.uniform(1500, 2500))
        human_type(page, ANSWER[mitad:], rng)
    elif escenario == "pegado_masivo":
        human_type(page, INTRO, rng)
        paste_block(page, PASTED)
    elif escenario == "cambios_foco":
        trozos = [ANSWER[i:i + len(ANSWER) // 8 + 1] for i in range(0, len(ANSWER), len(ANSWER) // 8 + 1)]
        for i, trozo in enumerate(trozos):
            human_type(page, trozo, rng)
            if i < 7:
                tab_out(page, rng.uniform(1500, 3000))
    elif escenario == "transcripcion":
        steady_type(page, ANSWER)
    else:
        raise ValueError(escenario)
    human_mouse(page, rng, 12)


# ---------------------------------------------------------------- API y verificaciones

def api_call(api: str, method: str, path: str, token: str | None = None, body: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{api}{path}", data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read() or b"null")


def leaked_text(db_path: Path, session_id: str) -> list[str]:
    """Devuelve problemas encontrados en los eventos guardados (vacío = ningún texto de la respuesta llegó a la base)."""
    palabras = {w.lower() for w in re.findall(r"[A-Za-z]{5,}", ANSWER + " " + PASTED + " " + INTRO)}
    problemas = []
    con = sqlite3.connect(db_path)
    try:
        for typ, payload in con.execute("SELECT type, payload FROM events WHERE session_id = ?", (session_id,)):
            p = json.loads(payload) if isinstance(payload, str) else (payload or {})
            extra = set(p) - PAYLOAD_KEYS
            if extra:
                problemas.append(f"{typ}: claves inesperadas {sorted(extra)}")
            if typ in ("keydown", "keyup") and ("code" in p or "key" in p):
                problemas.append(f"{typ}: identifica la tecla pulsada")
            for v in p.values():
                if isinstance(v, str) and len(v) > 12:
                    problemas.append(f"{typ}: string largo en payload")
                if isinstance(v, str) and v.lower() in palabras:
                    problemas.append(f"{typ}: contiene una palabra de la respuesta")
    finally:
        con.close()
    return problemas


CONTINUAS = ["mean_dwell_time_ms", "std_dwell_time_ms", "mean_flight_time_ms", "mean_mouse_speed_px_ms",
             "std_mouse_speed_px_ms"]  # = app/processing/anomaly.py::CONTINUOUS_METRICS


def zscores_vs_baseline(api: str, token: str, exam_id: str, sid: str) -> dict[str, float]:
    """z de cada métrica continua de la sesión frente a la línea base sintética del mismo examen.
    El backend solo expone el puntaje del IF cuando la sesión resulta atípica; esto permite
    interpretar también los casos no marcados (mismo cálculo que anomaly._top_deviating_features)."""
    base = [api_call(api, "GET", f"/sessions/{s['id']}", token)
            for s in api_call(api, "GET", f"/sessions?exam_id={exam_id}", token)
            if s["participant_id"].startswith("SINT-")]
    target = api_call(api, "GET", f"/sessions/{sid}", token)
    out = {}
    for name in CONTINUAS:
        col = [v for v in (metric(d, name) for d in base) if v is not None]
        x = metric(target, name)
        if len(col) < 2 or x is None:
            continue
        mu = sum(col) / len(col)
        sd = (sum((c - mu) ** 2 for c in col) / len(col)) ** 0.5
        out[name] = (x - mu) / sd if sd > 0 else 0.0
    return out


def metric(detail: dict, name: str) -> float | None:
    for m in detail["metrics"]:
        if m["name"] == name and m["item_ref"] is None:
            return m["value"]
    return None


# ---------------------------------------------------------------- reporte

def fmt(v, nd=1):
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.{nd}f}".replace(".", ",")
    return str(v)


def write_outputs(rows: list[dict], meta: dict, out: Path, sufijo: str = "") -> None:
    out.mkdir(parents=True, exist_ok=True)
    cols = ["escenario", "repeticion", "participante", "eventos", "requiere_revision", "indicadores_regla",
            "indicador_modelo", "estado_modelo", "esperados", "conforme", "ui_coincide", "sin_texto_en_eventos",
            "respuesta_guardada", "procesada",
            "paste_chars_total", "tab_switch_count", "focus_loss_duration_total_ms", "keydown_count",
            "mean_dwell_time_ms", "std_dwell_time_ms", "mean_flight_time_ms", "mean_mouse_speed_px_ms",
            "z_max_metrica", "z_max", "duracion_s"]
    with open(out / f"prueba_interna{sufijo}.csv", "w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        wr.writeheader()
        for r in rows:
            wr.writerow({**r, "indicadores_regla": "|".join(r["indicadores_regla"]),
                         "esperados": "|".join(sorted(r["esperados"]))})
    with open(out / f"prueba_interna{sufijo}.json", "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "sesiones": [{**r, "esperados": sorted(r["esperados"])} for r in rows]},
                  f, ensure_ascii=False, indent=2)

    L = []
    L.append("# Prueba interna end-to-end — resultados generados\n")
    L.append(f"_Generado por `scripts/prueba_interna.py` el {meta['fecha_utc']} (UTC). No editar a mano: "
             "la interpretación está en `prueba_interna.md`._\n")
    L.append(f"- Repeticiones por escenario: {meta['repeticiones']} · semilla del guion: {meta['semilla']} · "
             f"línea base: {meta['normales_linea_base']} sesiones sintéticas normales (semilla {meta['semilla_linea_base']}).")
    L.append(f"- Navegador: Chromium {meta['chromium']} (Playwright, headless) · Python {meta['python']} · {meta['plataforma']}.")
    L.append(f"- Duración total: {fmt(meta['duracion_total_min'])} min.\n")

    L.append("## Resumen por escenario\n")
    L.append("| Escenario | Guion | Indicador de regla esperado | Conformes | Indicador del modelo (IF) | UI = API | Sin texto en eventos | Respuesta guardada |")
    L.append("|---|---|---|---|---|---|---|---|")
    for esc in meta["escenarios"]:
        rs = [r for r in rows if r["escenario"] == esc]
        if not rs:
            continue
        n = len(rs)
        esp = ", ".join(f"`{k}`" for k in sorted(ESPERADOS[esc])) or "ninguno"
        L.append(f"| `{esc}` | {DESCRIPCION[esc]} | {esp} | {sum(r['conforme'] for r in rs)}/{n} | "
                 f"{sum(r['indicador_modelo'] for r in rs)}/{n} | {sum(r['ui_coincide'] for r in rs)}/{n} | "
                 f"{sum(r['sin_texto_en_eventos'] for r in rs)}/{n} | {sum(r['respuesta_guardada'] for r in rs)}/{n} |")
    L.append("\n_Conforme_ = se generaron todos los indicadores de regla esperados y ningún otro indicador de regla. "
             "El indicador del modelo poblacional se informa aparte: desde el Incremento 16 se calcula al cerrar la "
             "evaluación, sobre la cohorte completa (línea base sintética + la sesión de navegador).\n")

    L.append("## Detalle por sesión\n")
    L.append("| Escenario | Rep. | Eventos | Indicadores de regla | IF | Pegado (car.) | Cambios pestaña | Fuera de foco (s) | Pulsación media (ms) | Desvío pulsación (ms) | Entre teclas (ms) | Mouse (px/ms) | Mayor desvío vs. línea base (z) |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        ind = ", ".join(f"`{k}`" for k in r["indicadores_regla"]) or "—"
        fl = r["focus_loss_duration_total_ms"]
        L.append(f"| `{r['escenario']}` | {r['repeticion']} | {r['eventos']} | {ind} | {'sí' if r['indicador_modelo'] else 'no'} | "
                 f"{fmt(r['paste_chars_total'], 0)} | {fmt(r['tab_switch_count'], 0)} | {fmt(fl / 1000 if fl is not None else None)} | "
                 f"{fmt(r['mean_dwell_time_ms'])} | {fmt(r['std_dwell_time_ms'])} | {fmt(r['mean_flight_time_ms'])} | "
                 f"{fmt(r['mean_mouse_speed_px_ms'], 2)} | "
                 f"{('`' + r['z_max_metrica'] + '` ' + fmt(r['z_max'])) if r['z_max_metrica'] else '—'} |")
    if any(r["problemas_privacidad"] for r in rows):
        L.append("\n## Problemas de privacidad detectados\n")
        for r in rows:
            for p in r["problemas_privacidad"]:
                L.append(f"- `{r['escenario']}` rep. {r['repeticion']}: {p}")
    (out / f"prueba_interna{sufijo}_resultados.md").write_text("\n".join(L) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- main

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--backend-python", default=sys.executable)
    ap.add_argument("--api-port", type=int, default=8010)
    ap.add_argument("--web-port", type=int, default=5173)  # CORS del backend permite localhost:5173
    ap.add_argument("--repeticiones", type=int, default=3)
    ap.add_argument("--escenarios", nargs="+", choices=ESCENARIOS, default=ESCENARIOS)
    ap.add_argument("--normales", type=int, default=24, help="sesiones sintéticas de línea base por escenario (0 = sin modelo)")
    ap.add_argument("--semilla", type=int, default=18)
    ap.add_argument("--salida", type=Path, default=OUT_DEFAULT)
    ap.add_argument("--capturas", type=Path, default=None, help="carpeta para PNG del detalle docente (opcional)")
    ap.add_argument("--sin-build", action="store_true")
    ap.add_argument("--sufijo", default="", help="sufijo de los archivos de salida (p. ej. _inc16)")
    args = ap.parse_args(argv)
    args.backend_python = resolve_python(args.backend_python)

    t0 = time.time()
    tmp = Path(tempfile.mkdtemp(prefix="improntia-prueba-"))
    db_path = tmp / "prueba.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_path}", "VITE_API_URL": f"http://localhost:{args.api_port}"}
    api = f"http://127.0.0.1:{args.api_port}"
    web = f"http://localhost:{args.web_port}"
    procs: list[subprocess.Popen] = []
    log = open(tmp / "servidores.log", "w")
    rows: list[dict] = []
    if args.capturas:
        args.capturas.mkdir(parents=True, exist_ok=True)

    try:
        # El backend arranca primero para que aplique las migraciones sobre la base vacía (ver capturas_demo.py).
        procs.append(subprocess.Popen([args.backend_python, "-m", "uvicorn", "app.main:app", "--port", str(args.api_port)],
                                      cwd=BACKEND, env=env, stdout=log, stderr=subprocess.STDOUT))
        wait_http(f"{api}/health")
        subprocess.run([args.backend_python, "-m", "scripts.seed_teacher", EMAIL, PASSWORD], cwd=BACKEND, env=env,
                       check=True, stdout=log, stderr=subprocess.STDOUT)
        if not args.sin_build:
            subprocess.run(["npm", "run", "build"], cwd=DASHBOARD, env=env, check=True, stdout=log, stderr=subprocess.STDOUT)
        procs.append(subprocess.Popen(["npx", "vite", "preview", "--port", str(args.web_port), "--strictPort"],
                                      cwd=DASHBOARD, env=env, stdout=log, stderr=subprocess.STDOUT))
        wait_http(f"{api}/health")
        wait_http(web)
        token = api_call(api, "POST", "/auth/login", body={"email": EMAIL, "password": PASSWORD})["access_token"]

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            chromium_version = browser.version
            teacher = browser.new_context(viewport={"width": 1280, "height": 900}, locale="es-AR")
            tp = teacher.new_page()
            tp.goto(f"{web}/login")
            tp.fill("input[type=email]", EMAIL)
            tp.fill("input[type=password]", PASSWORD)
            tp.click("button[type=submit]")
            tp.wait_for_url("**/exams")

            for rep in range(1, args.repeticiones + 1):
                for k, esc in enumerate(args.escenarios):
                    rng = random.Random(args.semilla * 1000 + rep * 10 + k)
                    t_esc = time.time()
                    exam = api_call(api, "POST", "/exams", token, {
                        "name": f"Prueba interna — {esc} (rep. {rep})",
                        "info_text": "Prueba interna automatizada: se registran metadatos de interacción (no el texto).",
                        "rules_text": "Libro cerrado.",
                        "prompt_text": "Explicá la diferencia entre una clave primaria y una clave foránea.",
                        "allowed_signals": ["keyboard", "mouse", "scroll", "visibility", "clipboard"],
                    })
                    if args.normales > 0:
                        subprocess.run([args.backend_python, "-m", "scripts.seed_demo", "--api", api,
                                        "--join-code", exam["join_code"], "--normales", str(args.normales),
                                        "--atipicas", "0", "--semilla", "7"],
                                       cwd=BACKEND, env=env, check=True, stdout=log, stderr=subprocess.STDOUT)

                    participante = f"PI-{esc.upper()}-{rep:02d}"
                    student = browser.new_context(viewport={"width": 1280, "height": 800}, locale="es-AR")
                    sp = student.new_page()
                    sp.goto(f"{web}/exam/{exam['join_code']}")
                    sp.wait_for_selector("text=Qué se registra")
                    sp.fill("input[placeholder^='ej. P-017']", participante)
                    sp.check("input[type=checkbox]")
                    sp.click("button[type=submit]")
                    sp.wait_for_selector("text=Consigna")
                    run_scenario_actions(sp, esc, rng)
                    sp.get_by_role("button", name="Finalizar y entregar").click()
                    sp.get_by_role("button", name="Sí, entregar").click()  # diálogo de confirmación
                    sp.wait_for_selector("text=El servidor confirmó tu entrega", timeout=30000)
                    student.close()

                    # Incremento 16: el modelo poblacional corre al cerrar la evaluación (cohorte completa).
                    api_call(api, "POST", f"/exams/{exam['id']}/cerrar", token)

                    sesiones = api_call(api, "GET", f"/sessions?exam_id={exam['id']}", token)
                    sid = next(s["id"] for s in sesiones if s["participant_id"] == participante)
                    detail = api_call(api, "GET", f"/sessions/{sid}", token)
                    kinds = [i["kind"] for i in detail["indicators"]]
                    reglas = [k_ for k_ in kinds if k_ in REGLAS]

                    # Vista docente real: mismo número de indicadores y mismo estado que la API.
                    tp.goto(f"{web}/sessions/{sid}")
                    tp.wait_for_selector("text=Indicadores preliminares")
                    tp.wait_for_selector("text=Métricas calculadas")
                    ui_items = tp.locator(".indicator-item").count()
                    badge = "Requiere revisión" if detail["needs_review"] else "Sin indicadores"
                    ui_ok = ui_items == len(kinds) and tp.locator(f".page-head .chip:has-text('{badge}')").count() == 1
                    if args.capturas:
                        tp.screenshot(path=str(args.capturas / f"pi_{esc}_rep{rep}.png"), full_page=True)

                    problemas = leaked_text(db_path, sid)
                    zs = zscores_vs_baseline(api, token, exam["id"], sid) if args.normales > 0 else {}
                    zmax = max(zs, key=lambda n: abs(zs[n])) if zs else None
                    row = {
                        "escenario": esc, "repeticion": rep, "participante": participante, "session_id": sid,
                        "eventos": detail["event_count"], "requiere_revision": detail["needs_review"],
                        "indicadores_regla": reglas, "indicador_modelo": MODELO in kinds,
                        "esperados": ESPERADOS[esc], "conforme": set(reglas) == ESPERADOS[esc],
                        "ui_coincide": ui_ok, "sin_texto_en_eventos": not problemas, "problemas_privacidad": problemas,
                        "estado_modelo": detail.get("estado_modelo"),
                        "respuesta_guardada": bool(detail.get("respuesta")) and detail["respuesta"].strip().startswith(
                            (ANSWER if esc != "pegado_masivo" else INTRO)[:20]),
                        "procesada": bool(detail.get("procesada")),
                        "explicacion_modelo": next((i["explanation"] for i in detail["indicators"] if i["kind"] == MODELO), None),
                        "z_vs_linea_base": zs,
                        "z_max_metrica": zmax, "z_max": round(zs[zmax], 2) if zmax else None,
                        "duracion_s": round(time.time() - t_esc, 1),
                    }
                    for name in ("paste_chars_total", "tab_switch_count", "focus_loss_duration_total_ms", "keydown_count",
                                 "mean_dwell_time_ms", "std_dwell_time_ms", "mean_flight_time_ms", "mean_mouse_speed_px_ms"):
                        row[name] = metric(detail, name)
                    rows.append(row)
                    print(f"  [{esc} rep {rep}] eventos={row['eventos']} reglas={reglas or '-'} IF={row['indicador_modelo']} "
                          f"conforme={row['conforme']} ui={ui_ok} resp={row['respuesta_guardada']} privacidad={'OK' if not problemas else problemas[:2]} "
                          f"({row['duracion_s']} s)", flush=True)

            browser.close()

        meta = {
            "fecha_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
            "repeticiones": args.repeticiones, "escenarios": args.escenarios, "semilla": args.semilla,
            "normales_linea_base": args.normales, "semilla_linea_base": 7, "chromium": chromium_version,
            "python": platform.python_version(), "plataforma": platform.platform(terse=True),
            "duracion_total_min": (time.time() - t0) / 60, "esperados": {k: sorted(v) for k, v in ESPERADOS.items()},
            "descripcion": DESCRIPCION,
        }
        write_outputs(rows, meta, args.salida, args.sufijo)
        ok = all(r["conforme"] and r["ui_coincide"] and r["sin_texto_en_eventos"] and r["respuesta_guardada"]
                 and r["procesada"] for r in rows)
        print(f"\n{len(rows)} sesiones · conformes {sum(r['conforme'] for r in rows)}/{len(rows)} · "
              f"resultados en {args.salida}")
        return 0 if ok else 1
    finally:
        for p in procs:
            p.terminate()
        for p in procs:
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()
        log.close()
        print(f"(logs de servidores: {tmp / 'servidores.log'})")


if __name__ == "__main__":
    raise SystemExit(main())
