"""
Prueba end-to-end de resiliencia de la captura ante fallas de red (Incremento 10;
ver mvp/docs/bitacora.md y docs/evaluacion/prueba_red.md).

Cap. 15, "Captura de señales": reintentos con backoff, buffer local acotado y
registro como evento propio del agotamiento del buffer o de una falla
persistente, visible para la revisión docente. Este guion lo verifica sobre el
sistema REAL (backend FastAPI + dashboard compilado + Chromium):

- `corte_prolongado`: el estudiante escribe, se corta la red (Playwright aborta
  los POST a /events) durante ~60 s mientras sigue escribiendo, y vuelve. Se
  verifica que los intentos se espacian con backoff exponencial (5 -> 10 -> 20
  -> 40 s, ±20 %), que al reconectar llegan TODAS las pulsaciones (ninguna se
  pierde), que el backend registra un `sync_failure` y que el docente ve el
  indicador informativo `captura_incompleta` sin que la sesión quede priorizada.
- `buffer_lleno`: con la red cortada se generan más eventos que la capacidad
  del buffer (20 000). Se verifica que lo que no entra se cuenta y llega como
  `buffer_overflow`, y que eventos guardados + descartados = eventos generados.
- `reconexion`: corte breve avisado por el navegador (modo sin conexión de
  Playwright, que dispara `offline`/`online`): al volver la red se reintenta
  enseguida en lugar de esperar el próximo intento del backoff, y un corte
  breve no deja registro de falla persistente.

Uso (desde mvp/):

    python scripts/prueba_red.py --backend-python backend/.venv/bin/python
"""
import argparse
import json
import os
import random
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
from capturas_demo import EMAIL, PASSWORD, human_type, resolve_python, wait_http  # noqa: E402

MVP = Path(__file__).resolve().parent.parent
BACKEND = MVP / "backend"
DASHBOARD = MVP / "dashboard"
OUT_DEFAULT = MVP / "docs" / "evaluacion"

BASE_MS, MAX_MS, JITTER = 5_000, 60_000, 0.2  # = dashboard/src/syncQueue.ts DEFAULT_SYNC_CONFIG
BUFFER_CAP = 20_000
TEXTO_1 = "La clave primaria identifica cada fila. "
TEXTO_2 = "La clave foranea referencia otra tabla. "


def api_call(api: str, method: str, path: str, token: str | None = None, body: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{api}{path}", data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read() or b"null")


def metric(detail: dict, name: str):
    return next((m["value"] for m in detail["metrics"] if m["name"] == name and m["item_ref"] is None), None)


def stored_types(db_path: Path, sid: str) -> dict[str, int]:
    con = sqlite3.connect(db_path)
    try:
        return dict(con.execute("SELECT type, COUNT(*) FROM events WHERE session_id = ? GROUP BY type", (sid,)).fetchall())
    finally:
        con.close()


def stored_status_events(db_path: Path, sid: str) -> list[dict]:
    con = sqlite3.connect(db_path)
    try:
        rows = con.execute(
            "SELECT type, client_t, payload FROM events WHERE session_id = ? AND type IN ('sync_failure','buffer_overflow') ORDER BY seq",
            (sid,)).fetchall()
    finally:
        con.close()
    return [{"type": t, "t": ct, **(json.loads(p) if isinstance(p, str) else p)} for t, ct, p in rows]


def start_student(browser, web: str, join_code: str, participante: str) -> Page:
    ctx = browser.new_context(viewport={"width": 1280, "height": 800}, locale="es-AR")
    page = ctx.new_page()
    page.goto(f"{web}/exam/{join_code}")
    page.wait_for_selector("text=Qué se registra")
    page.fill("input[placeholder^='ej. P-017']", participante)
    page.check("input[type=checkbox]")
    page.click("button[type=submit]")
    page.wait_for_selector("text=Consigna")
    page.click("textarea")
    return page


def wait_synced(page: Page, timeout_ms: int = 90_000) -> None:
    page.wait_for_selector("text=/sincronizado \\(\\d+ eventos enviados\\)/", timeout=timeout_ms)


def escenario_corte(browser, api, web, token, db_path, rng) -> dict:
    exam = api_call(api, "POST", "/exams", token, {
        "name": "Prueba de red — corte prolongado", "info_text": "Prueba automatizada.", "rules_text": "-",
        "prompt_text": "Consigna de prueba.", "allowed_signals": ["keyboard"],
    })
    page = start_student(browser, web, exam["join_code"], "PR-CORTE-01")
    attempts: list[tuple[float, bool]] = []  # (instante, ¿con la red cortada?)
    offline = {"on": False}

    def on_route(route):
        attempts.append((time.time(), offline["on"]))
        if offline["on"]:
            route.abort("internetdisconnected")
        else:
            route.continue_()

    page.route("**/sessions/*/events", on_route)

    human_type(page, TEXTO_1, rng)
    wait_synced(page)
    offline["on"] = True
    t_off = time.time()
    human_type(page, TEXTO_2, rng)  # el estudiante sigue escribiendo sin conexión
    page.wait_for_selector("text=/sin conexión/", timeout=30_000)
    # Hasta la 3.ª falla consecutiva (~5 + 10 + 20 s después del corte) y un margen.
    while sum(1 for _, off in attempts if off) < 3:
        page.wait_for_timeout(500)
        if time.time() - t_off > 120:
            raise RuntimeError("no se registraron 3 intentos fallidos")
    status_offline = page.locator("[data-testid=sync-status]").inner_text()
    offline["on"] = False
    t_on = time.time()
    wait_synced(page, 90_000)
    t_synced = time.time()
    page.get_by_role("button", name="Finalizar y entregar").click()
    page.get_by_role("button", name="Sí, entregar").click()
    page.wait_for_selector("text=El servidor confirmó tu entrega", timeout=30_000)
    page.context.close()

    sid = next(s["id"] for s in api_call(api, "GET", f"/sessions?exam_id={exam['id']}", token))
    detail = api_call(api, "GET", f"/sessions/{sid}", token)
    kinds = [i["kind"] for i in detail["indicators"]]
    ind = next((i for i in detail["indicators"] if i["kind"] == "captura_incompleta"), None)

    # Intervalos entre intentos desde el último envío exitoso previo al corte.
    times = [t for t, _ in attempts]
    first_fail = next(i for i, (_, off) in enumerate(attempts) if off)
    seq = times[first_fail - 1:]
    gaps = [round(b - a, 1) for a, b in zip(seq, seq[1:])][:4]
    esperados = [min(MAX_MS, BASE_MS * 2 ** k) / 1000 for k in range(len(gaps))]
    backoff_ok = all(e * (1 - JITTER) - 1.0 <= g <= e * (1 + JITTER) + 1.5 for g, e in zip(gaps, esperados))
    teclas = len(TEXTO_1) + len(TEXTO_2)
    status = stored_status_events(db_path, sid)
    return {
        "escenario": "corte_prolongado",
        "session_id": sid,
        "corte_s": round(t_on - t_off, 1),
        "resincronizacion_s": round(t_synced - t_on, 1),
        "intervalos_s": gaps,
        "intervalos_esperados_s": esperados,
        "backoff_ok": backoff_ok,
        "texto_estudiante_sin_conexion": status_offline,
        "teclas_tipeadas": teclas,
        "keydown_guardados": metric(detail, "keydown_count"),
        "sin_perdida": metric(detail, "keydown_count") == teclas,
        "eventos_de_estado": status,
        "indicadores": kinds,
        "captura_incompleta": ind is not None,
        "requiere_revision": detail["needs_review"],
        "ok": backoff_ok and ind is not None and not detail["needs_review"]
              and metric(detail, "keydown_count") == teclas and metric(detail, "sync_failure_count") == 1,
    }


def escenario_buffer(browser, api, web, token, db_path, rng, extra: int) -> dict:
    exam = api_call(api, "POST", "/exams", token, {
        "name": "Prueba de red — buffer lleno", "info_text": "Prueba automatizada.", "rules_text": "-",
        "prompt_text": "Consigna de prueba.", "allowed_signals": ["keyboard"],
    })
    page = start_student(browser, web, exam["join_code"], "PR-BUFFER-01")
    offline = {"on": False}
    page.route("**/sessions/*/events", lambda r: r.abort("internetdisconnected") if offline["on"] else r.continue_())

    human_type(page, TEXTO_1, rng)
    wait_synced(page)
    offline["on"] = True
    generados = BUFFER_CAP + extra
    # Ráfaga de pulsaciones despachadas al documento: las registra el listener real de capture.ts.
    page.evaluate("""(n) => { for (let i = 0; i < n; i++) document.dispatchEvent(new KeyboardEvent('keydown')); }""",
                  generados)
    page.wait_for_selector("text=/sin conexión/", timeout=30_000)
    offline["on"] = False
    wait_synced(page, 90_000)
    page.get_by_role("button", name="Finalizar y entregar").click()
    page.get_by_role("button", name="Sí, entregar").click()
    page.wait_for_selector("text=El servidor confirmó tu entrega", timeout=60_000)
    page.context.close()

    sid = next(s["id"] for s in api_call(api, "GET", f"/sessions?exam_id={exam['id']}", token))
    detail = api_call(api, "GET", f"/sessions/{sid}", token)
    dropped = metric(detail, "capture_dropped_events")
    keydown = metric(detail, "keydown_count")
    capturados = len(TEXTO_1) + generados
    return {
        "escenario": "buffer_lleno",
        "session_id": sid,
        "eventos_generados_sin_conexion": generados,
        "capacidad_buffer": BUFFER_CAP,
        "keydown_guardados": keydown,
        "descartados_registrados": dropped,
        "cuadra": keydown + dropped == capturados,
        "eventos_de_estado": stored_status_events(db_path, sid),
        "tipos_guardados": stored_types(db_path, sid),
        "indicadores": [i["kind"] for i in detail["indicators"]],
        # `dropped` puede superar a `extra` en unos pocos eventos: los que todavía ocupaban el buffer
        # (sin enviar) en el instante del corte. Lo que se exige es que nada se pierda sin registro.
        "ok": dropped >= extra and keydown + dropped == capturados
              and any(i["kind"] == "captura_incompleta" for i in detail["indicators"]),
    }


def escenario_reconexion(browser, api, web, token, db_path, rng) -> dict:
    """Corte breve avisado por el navegador (`offline`/`online`): al volver la red se reintenta enseguida."""
    exam = api_call(api, "POST", "/exams", token, {
        "name": "Prueba de red — reconexión", "info_text": "Prueba automatizada.", "rules_text": "-",
        "prompt_text": "Consigna de prueba.", "allowed_signals": ["keyboard"],
    })
    page = start_student(browser, web, exam["join_code"], "PR-RECONEXION-01")
    human_type(page, TEXTO_1, rng)
    wait_synced(page)
    page.context.set_offline(True)
    human_type(page, TEXTO_2, rng)
    page.wait_for_selector("text=/sin conexión/", timeout=30_000)
    page.context.set_offline(False)
    t_on = time.time()
    wait_synced(page, 90_000)
    resync = round(time.time() - t_on, 1)
    page.get_by_role("button", name="Finalizar y entregar").click()
    page.get_by_role("button", name="Sí, entregar").click()
    page.wait_for_selector("text=El servidor confirmó tu entrega", timeout=30_000)
    page.context.close()
    sid = next(s["id"] for s in api_call(api, "GET", f"/sessions?exam_id={exam['id']}", token))
    detail = api_call(api, "GET", f"/sessions/{sid}", token)
    teclas = len(TEXTO_1) + len(TEXTO_2)
    return {
        "escenario": "reconexion",
        "session_id": sid,
        "resincronizacion_s": resync,
        "teclas_tipeadas": teclas,
        "keydown_guardados": metric(detail, "keydown_count"),
        "eventos_de_estado": stored_status_events(db_path, sid),
        "indicadores": [i["kind"] for i in detail["indicators"]],
        # Sin el aviso `online` el próximo intento llegaría recién a los ~10 s (backoff tras 1 falla).
        "ok": resync < 5 and metric(detail, "keydown_count") == teclas and not stored_status_events(db_path, sid),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--backend-python", default=sys.executable)
    ap.add_argument("--api-port", type=int, default=8010)
    ap.add_argument("--web-port", type=int, default=5173)
    ap.add_argument("--extra", type=int, default=5_000, help="eventos por encima de la capacidad del buffer")
    ap.add_argument("--salida", type=Path, default=OUT_DEFAULT)
    ap.add_argument("--sin-build", action="store_true")
    ap.add_argument("--capturas", type=Path, default=None,
                    help="carpeta para PNG del detalle docente de la sesión con corte (opcional)")
    args = ap.parse_args(argv)
    args.backend_python = resolve_python(args.backend_python)

    t0 = time.time()
    tmp = Path(tempfile.mkdtemp(prefix="improntia-red-"))
    db_path = tmp / "red.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_path}", "VITE_API_URL": f"http://localhost:{args.api_port}"}
    api = f"http://127.0.0.1:{args.api_port}"
    web = f"http://localhost:{args.web_port}"
    procs: list[subprocess.Popen] = []
    log = open(tmp / "servidores.log", "w")
    try:
        subprocess.run([args.backend_python, "-m", "scripts.seed_teacher", EMAIL, PASSWORD], cwd=BACKEND, env=env,
                       check=True, stdout=log, stderr=subprocess.STDOUT)
        procs.append(subprocess.Popen([args.backend_python, "-m", "uvicorn", "app.main:app", "--port", str(args.api_port)],
                                      cwd=BACKEND, env=env, stdout=log, stderr=subprocess.STDOUT))
        if not args.sin_build:
            subprocess.run(["npm", "run", "build"], cwd=DASHBOARD, env=env, check=True, stdout=log, stderr=subprocess.STDOUT)
        procs.append(subprocess.Popen(["npx", "vite", "preview", "--port", str(args.web_port), "--strictPort"],
                                      cwd=DASHBOARD, env=env, stdout=log, stderr=subprocess.STDOUT))
        wait_http(f"{api}/health")
        wait_http(web)
        token = api_call(api, "POST", "/auth/login", body={"email": EMAIL, "password": PASSWORD})["access_token"]

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            chromium = browser.version
            rng = random.Random(10)
            res = [escenario_corte(browser, api, web, token, db_path, rng),
                   escenario_buffer(browser, api, web, token, db_path, rng, args.extra),
                   escenario_reconexion(browser, api, web, token, db_path, rng)]
            if args.capturas:
                args.capturas.mkdir(parents=True, exist_ok=True)
                tp = browser.new_context(viewport={"width": 1280, "height": 800}, locale="es-AR").new_page()
                tp.goto(f"{web}/login")
                tp.fill("input[type=email]", EMAIL)
                tp.fill("input[type=password]", PASSWORD)
                tp.click("button[type=submit]")
                tp.wait_for_url("**/exams")
                tp.goto(f"{web}/sessions/{res[0]['session_id']}")
                tp.wait_for_selector("text=Métricas calculadas")
                tp.screenshot(path=str(args.capturas / "16_detalle_captura_incompleta.png"), full_page=True)
            browser.close()

        meta = {"fecha_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"), "chromium": chromium,
                "duracion_min": round((time.time() - t0) / 60, 1)}
        args.salida.mkdir(parents=True, exist_ok=True)
        (args.salida / "prueba_red.json").write_text(json.dumps({"meta": meta, "escenarios": res}, ensure_ascii=False, indent=2))
        c, b, rc = res
        L = [
            "# Prueba de resiliencia de la captura ante fallas de red — resultados generados\n",
            f"_Generado por `scripts/prueba_red.py` el {meta['fecha_utc']} (UTC), Chromium {chromium}, "
            f"{meta['duracion_min']} min. No editar a mano: la interpretación está en `prueba_red.md`._\n",
            "## Corte prolongado\n",
            "| Verificación | Resultado |", "|---|---|",
            f"| Corte de red simulado | {c['corte_s']} s (los POST a `/events` se abortan) |",
            f"| Intervalos entre intentos (s) | {', '.join(str(g) for g in c['intervalos_s'])} |",
            f"| Esperado con backoff (s, ±20 %) | {', '.join(str(int(e)) for e in c['intervalos_esperados_s'])} |",
            f"| Backoff dentro de la banda | {'sí' if c['backoff_ok'] else 'NO'} |",
            f"| Mensaje al estudiante sin conexión | «{c['texto_estudiante_sin_conexion']}» |",
            f"| Pulsaciones tipeadas / guardadas | {c['teclas_tipeadas']} / {int(c['keydown_guardados'])} "
            f"({'ninguna perdida' if c['sin_perdida'] else 'HAY PÉRDIDA'}) |",
            f"| Resincronización tras volver la red | {c['resincronizacion_s']} s |",
            f"| Eventos de estado guardados | {json.dumps(c['eventos_de_estado'], ensure_ascii=False)} |",
            f"| Indicadores | {', '.join(c['indicadores']) or '—'} |",
            f"| Requiere revisión | {'sí' if c['requiere_revision'] else 'no'} |",
            f"| **Conforme** | **{'sí' if c['ok'] else 'NO'}** |",
            "\n## Buffer lleno\n",
            "| Verificación | Resultado |", "|---|---|",
            f"| Eventos generados sin conexión | {b['eventos_generados_sin_conexion']} (capacidad del buffer: {b['capacidad_buffer']}) |",
            f"| Pulsaciones guardadas / descartadas registradas | {int(b['keydown_guardados'])} / {int(b['descartados_registrados'])} |",
            f"| Guardadas + descartadas = capturadas | {'sí' if b['cuadra'] else 'NO'} |",
            f"| Eventos de estado guardados | {json.dumps(b['eventos_de_estado'], ensure_ascii=False)} |",
            f"| Indicadores | {', '.join(b['indicadores']) or '—'} |",
            f"| **Conforme** | **{'sí' if b['ok'] else 'NO'}** |",
            "\n## Reconexión avisada por el navegador\n",
            "| Verificación | Resultado |", "|---|---|",
            f"| Resincronización tras el evento `online` | {rc['resincronizacion_s']} s (sin el aviso: próximo intento a los ~10 s) |",
            f"| Pulsaciones tipeadas / guardadas | {rc['teclas_tipeadas']} / {int(rc['keydown_guardados'])} |",
            f"| Eventos de estado guardados | {json.dumps(rc['eventos_de_estado'], ensure_ascii=False) if rc['eventos_de_estado'] else 'ninguno (corte breve: no es una falla persistente)'} |",
            f"| Indicadores | {', '.join(rc['indicadores']) or '—'} |",
            f"| **Conforme** | **{'sí' if rc['ok'] else 'NO'}** |",
        ]
        (args.salida / "prueba_red_resultados.md").write_text("\n".join(L) + "\n", encoding="utf-8")
        for r in res:
            print(json.dumps({k: v for k, v in r.items() if k != "tipos_guardados"}, ensure_ascii=False))
        return 0 if all(r["ok"] for r in res) else 1
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
