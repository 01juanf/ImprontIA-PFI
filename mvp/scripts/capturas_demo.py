"""
Capturas de pantalla de la demo de punta a punta (Incremento 7, ver
mvp/docs/bitacora.md): levanta backend + dashboard con una base SQLite
temporal, recorre con un navegador real (Playwright/Chromium) el flujo
crear evaluación -> rendir y entregar -> cerrar la evaluación -> ver
indicadores -> revisar, y guarda PNG numeradas en mvp/docs/capturas/.

Incremento 16: el estudiante entrega su respuesta al finalizar y la entrega se
confirma solo cuando el servidor procesó la sesión (06_entrega_confirmada). El
modelo poblacional se ejecuta una sola vez, al cerrar la evaluación desde el
dashboard (17_cierre_evaluacion): por eso el cierre ocurre antes de mirar las
sesiones, el indicador del modelo y el panorama.

Las PNG se regeneran en local corriendo este script. Lo que se muestra en cada una está
descripto en la bitácora.

Requisitos: backend instalado (requirements.txt), `npm install` hecho en
dashboard/, y Playwright para Python con Chromium (`pip install playwright`
+ `playwright install chromium`). El backend puede correr con otro
intérprete que el de este script (`--backend-python`), útil si Playwright
está instalado en un Python distinto al del venv del backend.

Uso (desde mvp/):

    python scripts/capturas_demo.py
    python scripts/capturas_demo.py --backend-python backend/.venv/bin/python --salida /tmp/capturas
"""
import argparse
import os
import random
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import Page, expect, sync_playwright

MVP = Path(__file__).resolve().parent.parent
BACKEND = MVP / "backend"
DASHBOARD = MVP / "dashboard"

EMAIL, PASSWORD = "docente.demo@uade.edu.ar", "demo1234"

EXAM = {
    "name": "Parcial 1 — Bases de Datos (demo)",
    "info": (
        "Durante esta evaluación la plataforma registra metadatos de interacción: tiempos de pulsación de "
        "teclas (no el texto), movimiento del mouse, cambios de pestaña y cantidad de caracteres pegados. "
        "Se usan solo para priorizar la revisión docente; ninguna decisión es automática."
    ),
    "rules": "Examen a libro cerrado. No está permitido consultar material externo ni otras pestañas.",
    "prompt": (
        "Explicá con tus palabras la diferencia entre una clave primaria y una clave foránea, "
        "y da un ejemplo de cada una en un modelo de alumnos y cursos."
    ),
}

ANSWER = (
    "La clave primaria identifica de forma unica cada fila de una tabla. "
    "La clave foranea referencia la clave primaria de otra tabla. "
)
PASTED = (
    "Una clave primaria (PK) es un atributo o conjunto de atributos que identifica univocamente cada tupla de "
    "una relacion; no admite valores nulos ni repetidos. Una clave foranea (FK) es un atributo de una relacion "
    "cuyos valores deben coincidir con los de la clave primaria de otra relacion, garantizando la integridad "
    "referencial. Ejemplo: en ALUMNO(legajo PK, nombre) y CURSO(codigo PK, nombre), la tabla INSCRIPCION(legajo "
    "FK, codigo FK) vincula ambas entidades."
)


def resolve_python(exe: str) -> str:
    """
    Ruta absoluta del intérprete del backend si se pasó como ruta relativa.

    Los procesos del backend se lanzan con `cwd=backend/`, y en POSIX una ruta
    relativa del ejecutable se resuelve contra ese `cwd`: sin esto,
    `--backend-python backend/.venv/bin/python` (corrido desde mvp/) fallaba con
    FileNotFoundError. Un nombre sin separador (p. ej. `python3`) se deja igual
    para que lo busque el PATH.
    """
    if os.sep in exe or (os.altsep and os.altsep in exe):
        return str(Path(exe).expanduser().absolute())
    return exe


def wait_http(url: str, timeout: float = 60.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status < 500:
                    return
        except Exception:
            time.sleep(0.5)
    raise RuntimeError(f"No respondió {url} en {timeout}s")


def human_type(page: Page, text: str, rng: random.Random) -> None:
    """Tecleo con dwell/flight variables (keyboard.type de Playwright tiene dwell ~0 ms, que el
    pipeline marcaría correctamente como `ritmo_tecleo_atipico`)."""
    for ch in text:
        key = "Space" if ch == " " else ch
        page.keyboard.down(key)
        page.wait_for_timeout(rng.uniform(60, 130))
        page.keyboard.up(key)
        page.wait_for_timeout(rng.uniform(70, 220))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--backend-python", default=sys.executable)
    ap.add_argument("--api-port", type=int, default=8010)
    ap.add_argument("--web-port", type=int, default=5173)  # CORS del backend permite localhost:5173
    ap.add_argument("--salida", type=Path, default=MVP / "docs" / "capturas")
    ap.add_argument("--normales", type=int, default=24, help="sesiones sintéticas de línea base")
    ap.add_argument("--sin-build", action="store_true", help="no correr `npm run build` (usa dist/ existente)")
    args = ap.parse_args(argv)
    args.backend_python = resolve_python(args.backend_python)

    out: Path = args.salida
    out.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="improntia-demo-"))
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{tmp / 'demo.db'}", "VITE_API_URL": f"http://localhost:{args.api_port}"}
    api = f"http://127.0.0.1:{args.api_port}"
    web = f"http://localhost:{args.web_port}"
    procs: list[subprocess.Popen] = []
    log = open(tmp / "servidores.log", "w")

    try:
        # El backend arranca primero: al iniciar aplica las migraciones (Alembic) sobre la base vacía.
        # Si seed_teacher corriera antes, su create_all dejaría tablas sin `alembic_version` y el
        # arranque fallaría al reaplicar 0002 (columna duplicada).
        procs.append(subprocess.Popen(
            [args.backend_python, "-m", "uvicorn", "app.main:app", "--port", str(args.api_port)],
            cwd=BACKEND, env=env, stdout=log, stderr=subprocess.STDOUT))
        wait_http(f"{api}/health")
        subprocess.run([args.backend_python, "-m", "scripts.seed_teacher", EMAIL, PASSWORD], cwd=BACKEND, env=env, check=True)
        if not args.sin_build:
            subprocess.run(["npm", "run", "build"], cwd=DASHBOARD, env=env, check=True, stdout=log, stderr=subprocess.STDOUT)
        procs.append(subprocess.Popen(
            ["npx", "vite", "preview", "--port", str(args.web_port), "--strictPort"],
            cwd=DASHBOARD, env=env, stdout=log, stderr=subprocess.STDOUT))
        wait_http(f"{api}/health")
        wait_http(web)

        rng = random.Random(15)
        shots: list[str] = []

        def set_filter(page: Page, value: bool) -> None:
            # El filtro «Solo sesiones que requieren revisión» vive en la URL (?revision=1): la casilla
            # cambia después de la navegación, así que se hace clic y se espera el estado final.
            # Rediseño (nov. 2026): el filtro es un control segmentado «Todas / Requieren revisión».
            btn = page.locator(".segmented button").nth(1 if value else 0)
            btn.click()
            expect(btn).to_have_attribute("aria-pressed", "true", timeout=5000)

        def shot(page: Page, name: str) -> None:
            path = out / f"{name}.png"
            page.screenshot(path=str(path), full_page=True)
            shots.append(path.name)
            print(f"  captura: {path.name}")

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            teacher = browser.new_context(viewport={"width": 1280, "height": 800}, locale="es-AR", timezone_id="America/Argentina/Buenos_Aires")
            tp = teacher.new_page()

            # 1. Login docente
            tp.goto(f"{web}/login")
            tp.fill("input[type=email]", EMAIL)
            tp.fill("input[type=password]", PASSWORD)
            shot(tp, "01_login_docente")
            tp.click("button[type=submit]")
            tp.wait_for_url("**/exams")

            # 2. Crear evaluación (RF01, RF02, RF04)
            tp.get_by_role("link", name="Nueva evaluación").first.click()
            tp.fill("input[placeholder^='ej. Parcial']", EXAM["name"])
            areas = tp.locator("form textarea")
            # Orden del formulario nuevo: consigna, información previa (precompletada), reglas.
            areas.nth(0).fill(EXAM["prompt"])
            areas.nth(1).fill(EXAM["info"])
            areas.nth(2).fill(EXAM["rules"])
            shot(tp, "02_crear_evaluacion")
            tp.get_by_role("button", name="Crear evaluación").click()
            tp.wait_for_selector(".created .code-big")
            join_code = tp.locator(".created .code-big").inner_text().strip()
            shot(tp, "03_evaluacion_creada")
            print(f"  join_code = {join_code}")

            # 3. Línea base poblacional sintética (vía API real) + una sesión atípica solo detectable por el modelo
            subprocess.run([args.backend_python, "-m", "scripts.seed_demo", "--api", api, "--join-code", join_code,
                            "--normales", str(args.normales), "--atipicas", "1"], cwd=BACKEND, env=env, check=True)

            # 4. Vista del estudiante (otro contexto: sin token docente)
            student = browser.new_context(viewport={"width": 1280, "height": 800}, locale="es-AR")
            sp = student.new_page()
            sp.goto(f"{web}/exam/{join_code}")
            sp.wait_for_selector("text=Qué se registra")
            sp.fill("input[placeholder^='ej. P-017']", "EST-DEMO-01")
            sp.check("input[type=checkbox]")
            shot(sp, "04_estudiante_info_y_consentimiento")
            sp.click("button[type=submit]")
            sp.wait_for_selector("text=Consigna")
            sp.click("textarea")
            sp.mouse.move(300, 300)
            sp.mouse.move(700, 450, steps=12)
            human_type(sp, ANSWER, rng)
            # Pegado de un bloque de texto: se dispara el evento `paste` real del DOM (capture.ts solo
            # registra la longitud) y se inserta el texto en el textarea sin eventos de teclado.
            sp.evaluate(
                """(text) => {
                    const ta = document.querySelector('textarea');
                    const dt = new DataTransfer();
                    dt.setData('text', text);
                    ta.dispatchEvent(new ClipboardEvent('paste', { clipboardData: dt, bubbles: true }));
                }""",
                PASTED,
            )
            sp.keyboard.insert_text(PASTED)
            sp.wait_for_selector("text=/sincronizado \\(\\d+ eventos enviados\\)/", timeout=15000)
            shot(sp, "05_estudiante_rindiendo")
            sp.get_by_role("button", name="Finalizar y entregar").click()
            sp.get_by_role("button", name="Sí, entregar").click()  # confirmación en línea de la entrega
            # Incremento 16: la entrega (con la respuesta) se confirma solo cuando el servidor la procesó.
            sp.wait_for_selector("text=El servidor confirmó tu entrega", timeout=30000)
            shot(sp, "06_entrega_confirmada")

            # 5. Docente: cierre de la evaluación, que ejecuta el modelo sobre la cohorte completa (Incremento 16)
            tp.goto(f"{web}/exams")
            tp.locator(".exam-row .row-link").first.click()  # las abiertas van primero
            tp.wait_for_selector("table")
            tp.get_by_role("button", name="Cerrar y analizar").click()
            tp.get_by_role("button", name="Confirmar el cierre").click()
            tp.wait_for_selector("text=Evaluación cerrada.", timeout=60000)
            tp.wait_for_selector("td:text-is('Con marca')")  # la lista se recarga con el estado del modelo
            # 17: la tarjeta después del cierre, con el resultado del modelo («El modelo marcó N de M…»).
            tp.wait_for_selector("[data-testid=close-summary]", timeout=20000)
            close_card = tp.locator(".stats")
            close_card.scroll_into_view_if_needed()
            close_card.screenshot(path=str(out / "17_cierre_evaluacion.png"))
            shots.append("17_cierre_evaluacion.png")
            print("  captura: 17_cierre_evaluacion.png")

            # 6. Docente: sesiones de la evaluación (RF07)
            shot(tp, "07_sesiones_de_la_evaluacion")
            set_filter(tp, True)
            tp.wait_for_timeout(800)
            shot(tp, "08_sesiones_filtro_requiere_revision")

            # 6b. Detalle de la sesión del estudiante: indicadores con su métrica de origen (RF09, RNF05/06)
            tp.click("tr:has-text('EST-DEMO-01') .pid")
            tp.wait_for_selector(".review-panel")
            shot(tp, "09_detalle_sesion_indicadores")

            # 7. Revisión docente (RF10/RF11)
            first_indicator = tp.locator(".indicator-item input[type=checkbox]").first
            if first_indicator.count():
                first_indicator.check()
            tp.fill("textarea", "Pegado de un bloque largo. Se cita al estudiante para una instancia oral.")
            tp.get_by_role("button", name="Requiere validación adicional").click()
            tp.wait_for_selector(".alert-success")
            shot(tp, "10_revision_docente_registrada")

            # 8. Sesión atípica para el modelo poblacional (Isolation Forest)
            tp.go_back()
            tp.wait_for_selector("table")
            set_filter(tp, False)
            tp.wait_for_selector("tr:has-text('SINT-ATIPICA-01')")
            tp.click("tr:has-text('SINT-ATIPICA-01') .pid")
            tp.wait_for_selector(".review-panel")
            shot(tp, "11_detalle_atipico_modelo_poblacional")

            # 9. Validaciones adicionales pendientes (RF11/HU08), de todas las evaluaciones
            tp.get_by_role("link", name=re.compile("Validaciones pendientes")).click()
            tp.wait_for_selector("tr:has-text('EST-DEMO-01')")
            shot(tp, "12_validaciones_pendientes")

            # 10. Cierre del pedido tras la validación externa: el historial conserva ambos registros
            tp.click("tr:has-text('EST-DEMO-01') .pid")
            tp.wait_for_selector("text=Historial")
            tp.fill("textarea", "Instancia oral realizada: el estudiante explicó el desarrollo. Sin observaciones.")
            tp.get_by_role("button", name="Marcar como revisada").click()
            tp.wait_for_selector(".timeline li:nth-child(3)")  # título + dos revisiones
            shot(tp, "13_historial_de_revision")

            # 11. Versionado de la política de captura (RNF04): editar crea una versión nueva
            tp.get_by_role("link", name="Evaluaciones").first.click()
            tp.locator(".exam-row .row-link").first.click()
            tp.get_by_role("tab", name="Configuración").click()
            tp.get_by_role("button", name="Editar (crea versión nueva)").click()
            tp.locator("section.card form textarea").nth(1).fill(
                EXAM["rules"] + " Se permite una hoja de fórmulas impresa.")
            tp.locator("section.card form label:has-text('Scroll') input").uncheck()
            section = tp.locator("section.card:has(h3:has-text('Política de captura'))")
            section.screenshot(path=str(out / "14_politica_edicion.png"))
            shots.append("14_politica_edicion.png")
            print("  captura: 14_politica_edicion.png")
            tp.get_by_role("button", name="Guardar como versión nueva").click()
            tp.wait_for_selector("text=Política de captura · versión 2")
            section.screenshot(path=str(out / "15_politica_version_2.png"))
            shots.append("15_politica_version_2.png")
            print("  captura: 15_politica_version_2.png")

            # 12. Panorama agregado de la evaluación (RF15, Incremento 12), con la cobertura del modelo
            tp.get_by_role("tab", name="Panorama").click()
            tp.wait_for_selector("[data-testid=panorama-cobertura]:has-text('sesiones evaluadas')")
            tp.wait_for_timeout(500)
            shot(tp, "16_panorama_evaluacion")

            browser.close()

        # Resumen de lo que mostró el backend para la sesión del estudiante (para la bitácora)
        print(f"\n{len(shots)} capturas en {out}")
        return 0
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
