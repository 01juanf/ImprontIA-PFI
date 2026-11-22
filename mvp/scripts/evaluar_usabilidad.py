"""
Evaluación experta y automatizada de usabilidad y navegabilidad del MVP
(inspección heurística + recorridos instrumentados con Playwright/Chromium).

NO es una prueba con usuarios: no hay participantes, ni SUS, ni opiniones. Los
tiempos son de la automatización (no tiempos humanos). Sirve para detectar
problemas antes de una prueba con docentes y estudiantes, no para reemplazarla.

Qué hace:
  1. Levanta backend (puerto 8100) y dashboard compilado con `vite preview` (5180)
     sobre una base SQLite temporal propia; no toca dashboard/dist ni la base local.
  2. Ejecuta las tareas T1–T9 (docente) y E1–E4 (estudiante) con un navegador real,
     contando acciones (clics + envíos de teclado; el tipeo de caracteres no cuenta),
     pantallas/rutas visitadas, errores de consola, requests fallidos y tiempo.
  3. Repite las tareas solo con teclado (Tab/Shift+Tab/Enter/Espacio).
  4. Navegabilidad: mapa de rutas y enlaces, profundidad, botón atrás, deep-link y
     recarga, rutas desconocidas, migas/volver, estado activo de la navegación.
  5. Por pantalla: tiempos de carga (DCL, load, LCP), CLS, axe-core (WCAG 2.1 A/AA),
     contraste, foco visible, etiquetas, desborde a 375×667 y 1366×768, tamaño mínimo de
     fuente, objetivos táctiles < 24 px, legibilidad (INFLESZ aproximado) e inventario
     de botones/terminología.
  Guarda capturas y `metricas.json` en docs/evaluacion/usabilidad/.

Requisitos: dependencias del backend + Playwright para Python con Chromium, `npm install`
hecho en dashboard/, y axe-core en una carpeta aparte (no en el repo):

    mkdir -p /tmp/axe && (cd /tmp/axe && npm install axe-core@4.10.2)

Uso (desde mvp/):

    python scripts/evaluar_usabilidad.py --axe /tmp/axe/node_modules/axe-core/axe.min.js
    python scripts/evaluar_usabilidad.py --api-port 8100 --web-port 5180 --backend-python ../venv/bin/python
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import signal
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import BrowserContext, Page, expect, sync_playwright

MVP = Path(__file__).resolve().parent.parent
BACKEND = MVP / "backend"
DASHBOARD = MVP / "dashboard"
OUT_DEFAULT = MVP / "docs" / "evaluacion" / "usabilidad"

EMAIL, PASSWORD = "docente.usab@uade.edu.ar", "usab1234"
DESKTOP = {"width": 1366, "height": 768}
MOBILE = {"width": 375, "height": 667}
WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]
# Casilla «Solo sesiones que requieren revisión». En la versión 1 estaba en .page-header; desde la
# corrección de usabilidad está en la barra de la tabla (.toolbar). Se aceptan las dos.
FILTER_SEL = ":is(.page-header, .toolbar) input[type=checkbox]"
# Paso de confirmación de la entrega (agregado en la corrección de usabilidad, problema 4).
CONFIRM_SUBMIT = re.compile(r"^(Sí, entregar|Confirmar la entrega)$")

EXAM_A = {
    "name": "Parcial 1 — Bases de Datos (usabilidad)",
    "info": ("Durante esta evaluación la plataforma registra metadatos de interacción: tiempos de pulsación de "
             "teclas (no el texto), movimiento del mouse, cambios de pestaña y cantidad de caracteres pegados. "
             "Se usan solo para priorizar la revisión docente; ninguna decisión es automática."),
    "rules": "Examen a libro cerrado. Se permite consultar la documentación oficial en otra pestaña.",
    "prompt": "Explicá la diferencia entre clave primaria y clave foránea, con un ejemplo de cada una.",
}
EXAM_B = {"name": "Recuperatorio (teclado)", "info": "Se registran tiempos de tecleo y cambios de pestaña.",
          "rules": "Libro cerrado.", "prompt": "Definí normalización."}
ANSWER = "La clave primaria identifica cada fila. La foranea referencia otra tabla. "
PASTED = ("Una clave primaria (PK) es un atributo que identifica univocamente cada tupla de una relacion; no admite "
          "nulos ni repetidos. Una clave foranea (FK) referencia la PK de otra relacion y garantiza la integridad "
          "referencial. Ejemplo: INSCRIPCION(legajo FK, codigo FK).")

# Punto de partida del recorrido de foco: el principio del documento (como al cargar la página).
FOCUS_TOP_JS = """() => { let a = document.getElementById('__eval_top');
  if (!a) { a = document.createElement('span'); a.id = '__eval_top'; a.tabIndex = -1; document.body.prepend(a); }
  window.scrollTo(0, 0); a.focus(); }"""
FOCUS_TOP_CLEAN_JS = "() => { const a = document.getElementById('__eval_top'); if (a) a.remove(); }"

UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")

PERF_INIT = """
window.__perf = {lcp: null, cls: 0, shifts: []};
try {
  new PerformanceObserver((l) => { for (const e of l.getEntries()) window.__perf.lcp = e.startTime; })
    .observe({type: 'largest-contentful-paint', buffered: true});
  new PerformanceObserver((l) => { for (const e of l.getEntries()) if (!e.hadRecentInput) {
      window.__perf.cls += e.value; window.__perf.shifts.push(e.value); } })
    .observe({type: 'layout-shift', buffered: true});
} catch (e) {}
"""

# Rutas declaradas en dashboard/src/App.tsx (fuente del mapa de rutas).
ROUTES = [
    {"ruta": "/login", "pantalla": "Login docente", "auth": False},
    {"ruta": "/rendir", "pantalla": "Ingreso del estudiante con el código", "auth": False},
    {"ruta": "/exam", "pantalla": "Ingreso del estudiante con el código (igual que /rendir)", "auth": False},
    {"ruta": "/exam/:joinCode", "pantalla": "Examen del estudiante (información → consigna → entrega)", "auth": False},
    {"ruta": "/exams", "pantalla": "Evaluaciones (inicio docente)", "auth": True},
    {"ruta": "/exams/:examId", "pantalla": "Redirige a /exams/:examId/sessions", "auth": True},
    {"ruta": "/exams/:examId/sessions", "pantalla": "Sesiones de una evaluación (pestañas Sesiones/Panorama, en la URL)", "auth": True},
    {"ruta": "/sessions/:sessionId", "pantalla": "Detalle de sesión", "auth": True},
    {"ruta": "/validaciones", "pantalla": "Validaciones pendientes", "auth": True},
    {"ruta": "/", "pantalla": "Redirige a /exams", "auth": True},
    {"ruta": "*", "pantalla": "Página «No encontrada» (NotFound.tsx)", "auth": False},
]


def norm_route(url: str) -> str:
    path = re.sub(r"^https?://[^/]+", "", url).split("?")[0].split("#")[0] or "/"
    path = UUID_RE.sub(":id", path)
    path = re.sub(r"^/exam/[^/]+$", "/exam/:joinCode", path)
    return path


def resolve_python(exe: str) -> str:
    if os.sep in exe or (os.altsep and os.altsep in exe):
        return str(Path(exe).expanduser().absolute())
    return exe


def wait_http(url: str, timeout: float = 90.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status < 500:
                    return
        except Exception:
            time.sleep(0.5)
    raise RuntimeError(f"No respondió {url} en {timeout}s")


def api_json(api: str, path: str, token: str | None = None, method: str = "GET", body: dict | None = None):
    req = urllib.request.Request(f"{api}{path}", method=method,
                                 data=json.dumps(body).encode() if body is not None else None)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        return e.code, None


def human_type(page: Page, text: str, rng: random.Random) -> None:
    """Tecleo con dwell/flight variables (no cuenta como acción: es tipeo de caracteres)."""
    for ch in text:
        key = "Space" if ch == " " else ch
        page.keyboard.down(key)
        page.wait_for_timeout(rng.uniform(40, 90))
        page.keyboard.up(key)
        page.wait_for_timeout(rng.uniform(40, 120))


# --------------------------------------------------------------------------------------
# Instrumentación de páginas y tareas
# --------------------------------------------------------------------------------------
class Monitor:
    """Escucha consola, errores de página, requests fallidos y navegaciones de cada página."""

    def __init__(self):
        self.log: list[dict] = []

    def attach(self, page: Page, label: str) -> Page:
        def add(kind, **kw):
            self.log.append({"t": time.perf_counter(), "page": label, "kind": kind, **kw})

        page.on("console", lambda m: add("console_error", text=m.text[:300]) if m.type == "error" else None)
        page.on("pageerror", lambda e: add("page_error", text=str(e)[:300]))
        page.on("requestfailed", lambda r: add("request_failed", url=norm_route(r.url), method=r.method,
                                                error=(r.failure or "")[:120]))
        page.on("response", lambda r: add("http_error", url=norm_route(r.url), method=r.request.method,
                                          status=r.status) if r.status >= 400 else None)
        page.on("framenavigated", lambda f: add("nav", route=norm_route(f.url)) if f == page.main_frame else None)

        # Un aviso beforeunload (examen en curso) se registra y se acepta, como haría quien
        # confirma que quiere salir; sin listener Playwright lo descartaría y la navegación no seguiría.
        def on_dialog(d):
            add("dialog", type=d.type, message=(d.message or "")[:120])
            try:
                d.accept()
            except Exception:
                pass
        page.on("dialog", on_dialog)
        return page

    def dialogs_since(self, t0: float, label: str | None = None) -> list[dict]:
        return [e for e in self.log if e["t"] >= t0 and e["kind"] == "dialog" and (label is None or e["page"] == label)]

    def since(self, t0: float, kinds: set[str]) -> list[dict]:
        return [{k: v for k, v in e.items() if k != "t"} for e in self.log if e["t"] >= t0 and e["kind"] in kinds]


class Task:
    def __init__(self, ev: "Evaluacion", tid: str, actor: str, desc: str, minimo: int, modo: str = "mouse"):
        self.ev, self.id, self.actor, self.desc, self.minimo, self.modo = ev, tid, actor, desc, minimo, modo
        self.acciones = 0
        self.teclas_tab = 0
        self.rutas: list[str] = []
        self.errores: list[str] = []
        self.observaciones: list[str] = []
        self.exito = False
        self.estado = "fallo"
        self.esperados_red: list[str] = []
        self.extra: dict = {}

    def __enter__(self):
        self.t0 = time.perf_counter()
        return self

    def _route(self, page: Page):
        r = norm_route(page.url)
        if not self.rutas or self.rutas[-1] != r:
            self.rutas.append(r)

    def start_at(self, page: Page, keep_focus: bool = False):
        """keep_focus: la pantalla tiene autofocus (login, código de participante) y se aprovecha."""
        if self.modo == "teclado" and not keep_focus:
            self.extra["foco_al_llegar"] = page.evaluate(
                "() => document.activeElement === document.body ? 'BODY' : document.activeElement.tagName + ' ' + (document.activeElement.innerText || '').trim().slice(0, 30)")
            page.evaluate(FOCUS_TOP_JS)  # se mide desde el principio de la página, como tras una carga
        self._route(page)

    # Acciones que cuentan (clic, envío de teclado, atrás, escribir una URL)
    def click(self, page: Page, target, **kw):
        loc = page.locator(target) if isinstance(target, str) else target
        loc.click(**kw)
        self.acciones += 1
        page.wait_for_timeout(150)
        self._route(page)

    def check(self, page: Page, target, value: bool = True):
        loc = page.locator(target) if isinstance(target, str) else target
        # Un clic (una acción), y se espera el estado final: las casillas cuyo valor vive en la
        # URL (filtro de Sesiones, ?revision=1) se actualizan después de la navegación, no en
        # el mismo instante del clic, y Locator.set_checked las daba por no cambiadas.
        if loc.is_checked() != value:
            loc.click()
        expect(loc).to_be_checked(checked=value, timeout=5000)
        self.acciones += 1
        self._route(page)

    def press(self, page: Page, key: str):
        page.keyboard.press(key)
        if key in ("Tab", "Shift+Tab"):
            self.teclas_tab += 1
        else:
            self.acciones += 1
        page.wait_for_timeout(60)
        self._route(page)

    def goto(self, page: Page, url: str):
        page.goto(url)
        self.acciones += 1
        page.wait_for_load_state("networkidle")
        self._route(page)

    def back(self, page: Page):
        page.go_back()
        self.acciones += 1
        page.wait_for_timeout(400)
        self._route(page)

    def tab_until(self, page: Page, pred_js: str, max_tabs: int = 120, shift: bool = False, report: bool = True) -> int | None:
        """Presiona Tab hasta que document.activeElement cumpla `pred_js` (función JS el => bool)."""
        for i in range(1, max_tabs + 1):
            self.press(page, "Shift+Tab" if shift else "Tab")
            if page.evaluate(f"(() => {{ const el = document.activeElement; return !!el && ({pred_js})(el); }})()"):
                return i
        if report:
            self.errores.append(f"No se alcanzó el elemento con Tab en {max_tabs} pulsaciones")
        return None

    def __exit__(self, exc_type, exc, tb):
        dt = time.perf_counter() - self.t0
        if exc is not None:
            self.exito = False
            self.estado = "fallo"
            self.errores.append(f"{exc_type.__name__}: {str(exc).splitlines()[0][:200]}")
        mon = self.ev.monitor.since(self.t0, {"console_error", "page_error", "request_failed", "http_error"})
        self.ev.tasks.append({
            "id": self.id, "actor": self.actor, "modo": self.modo, "descripcion": self.desc,
            "exito": self.exito, "estado": self.estado,
            "acciones": self.acciones, "acciones_minimas": self.minimo,
            "pulsaciones_tab": self.teclas_tab,
            "rutas_visitadas": self.rutas, "n_pantallas": len(set(self.rutas)),
            "tiempo_automatizacion_s": round(dt, 2),
            "errores_o_bloqueos": self.errores, "observaciones": [o for o in self.observaciones if o],
            "errores_consola": [m for m in mon if m["kind"] in ("console_error", "page_error")],
            "red_fallida": [m for m in mon if m["kind"] in ("request_failed", "http_error")],
            "red_fallida_esperada": self.esperados_red, **self.extra,
        })
        print(f"  [{self.id}/{self.modo}] {self.estado} · {self.acciones} acc (mín {self.minimo})"
              f"{f' · {self.teclas_tab} Tab' if self.teclas_tab else ''} · {dt:.1f}s")
        if self.estado == "fallo":
            print("      " + " | ".join(self.errores)[:400])
        return True  # una tarea fallida no corta la evaluación


# --------------------------------------------------------------------------------------
# Auditoría de pantalla (JS que corre en la página)
# --------------------------------------------------------------------------------------
LAYOUT_JS = r"""
() => {
  const vw = document.documentElement.clientWidth;
  const vis = (el) => { const r = el.getBoundingClientRect(); const cs = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none'; };
  const desc = (el) => { const t = (el.innerText || el.value || el.getAttribute('aria-label') || el.placeholder || '').trim().replace(/\s+/g,' ');
    return el.tagName.toLowerCase() + (el.className && typeof el.className === 'string' ? '.' + el.className.trim().split(/\s+/).join('.') : '') + (t ? ` "${t.slice(0,40)}"` : ''); };
  const all = [...document.querySelectorAll('body *')].filter(vis);
  const overflow = all.filter(el => el.getBoundingClientRect().right > vw + 1)
     .filter(el => !all.some(p => p !== el && p.contains(el) && p.getBoundingClientRect().right > vw + 1 && p.tagName !== 'BODY' && p.tagName !== 'MAIN' && !p.classList.contains('page') && !p.classList.contains('app-shell')))
     .slice(0, 12).map(el => ({el: desc(el), right: Math.round(el.getBoundingClientRect().right)}));
  const clipped = all.filter(el => { const cs = getComputedStyle(el);
      return (cs.overflowX === 'hidden' || cs.textOverflow === 'ellipsis') && el.scrollWidth > el.clientWidth + 1; })
     .slice(0, 10).map(desc);
  // fuentes: elementos con texto propio visible
  const sizes = {};
  for (const el of all) {
    const own = [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim().length > 0);
    if (!own) continue;
    const fs = parseFloat(getComputedStyle(el).fontSize);
    sizes[fs] = (sizes[fs] || 0) + 1;
  }
  const fsKeys = Object.keys(sizes).map(Number).sort((a,b)=>a-b);
  const interactive = [...document.querySelectorAll('a[href], button, input, select, textarea, [role=tab], [tabindex]:not([tabindex="-1"])')].filter(vis);
  const small = interactive.filter(el => { const r = el.getBoundingClientRect(); return r.width < 24 || r.height < 24; })
     .map(el => { const r = el.getBoundingClientRect(); return {el: desc(el), w: Math.round(r.width), h: Math.round(r.height)}; });
  // etiquetas de campos
  const fields = [...document.querySelectorAll('input, textarea, select')].filter(vis);
  const noLabel = fields.filter(f => { const lab = f.labels && f.labels.length > 0; const aria = f.getAttribute('aria-label') || f.getAttribute('aria-labelledby');
      return !lab && !aria; }).map(desc);
  const placeholderOnlyHint = fields.filter(f => f.placeholder && f.labels && f.labels.length && (f.labels[0].innerText||'').trim() === '').map(desc);
  const nav = [...document.querySelectorAll('.topnav a')].map(a => ({texto: a.innerText.trim(), activo: a.classList.contains('active'), aria_current: a.getAttribute('aria-current')}));
  const tabs = [...document.querySelectorAll('[role=tab]')].map(t => ({texto: t.innerText.trim(), aria_selected: t.getAttribute('aria-selected'), aria_controls: t.getAttribute('aria-controls')}));
  const tabpanels = document.querySelectorAll('[role=tabpanel]').length;
  const breadcrumbs = document.querySelectorAll('nav[aria-label*="breadcrumb" i], nav[aria-label*="migas" i], .breadcrumb, .breadcrumbs').length;
  const backLinks = [...document.querySelectorAll('a, button')].filter(vis).filter(el => /^(←|‹)|volver|regresar/i.test((el.innerText||'').trim())).map(desc);
  const controls = [...document.querySelectorAll('button, a.btn, [role=tab], a[href]')].filter(vis).map(el => ({texto: (el.innerText||'').trim().replace(/\s+/g,' '), clase: (el.className||'').toString(), tag: el.tagName.toLowerCase(), href: el.getAttribute('href')}));
  const h = document.querySelectorAll('h1, h2');
  return {
    viewport_w: vw, scroll_w: document.documentElement.scrollWidth, page_h: document.documentElement.scrollHeight,
    viewport_h: window.innerHeight, desborde_horizontal: document.documentElement.scrollWidth > vw + 1,
    elementos_desbordados: overflow, elementos_recortados: clipped,
    tamanos_fuente_px: sizes, fuente_min_px: fsKeys[0] || null, textos_menores_12px: fsKeys.filter(s => s < 12).reduce((a,s)=>a+sizes[s],0),
    interactivos: interactive.length, objetivos_menores_24px: small,
    campos: fields.length, campos_sin_etiqueta: noLabel, placeholder_sin_texto_label: placeholderOnlyHint,
    titulo_documento: document.title, encabezados: [...h].map(x => x.tagName + ': ' + x.innerText.trim().slice(0,80)),
    nav_superior: nav, pestanas: tabs, tabpanels, migas: breadcrumbs, enlaces_volver: backLinks, controles: controls,
    lang: document.documentElement.lang,
  };
}
"""

TEXT_JS = r"""
() => {
  const vis = (el) => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const blocks = [...document.querySelectorAll('p, li, dd, .callout, .field-hint, .alert, label')].filter(vis)
     .map(el => (el.innerText || '').trim().replace(/\s+/g, ' ')).filter(t => t.split(' ').length >= 8);
  return {bloques: [...new Set(blocks)], palabras_totales: (document.body.innerText || '').split(/\s+/).filter(Boolean).length};
}
"""

FOCUS_WALK_JS = r"""
() => { const el = document.activeElement; if (!el || el === document.body) return null;
  const cs = getComputedStyle(el); const r = el.getBoundingClientRect();
  const visible = (cs.outlineStyle !== 'none' && parseFloat(cs.outlineWidth) > 0) || (cs.boxShadow && cs.boxShadow !== 'none');
  return {tag: el.tagName.toLowerCase(), texto: (el.innerText || el.value || el.getAttribute('aria-label') || el.placeholder || el.type || '').trim().replace(/\s+/g,' ').slice(0,50),
          outline: cs.outlineStyle + ' ' + cs.outlineWidth, foco_visible: !!visible, en_pantalla: r.bottom > 0 && r.top < innerHeight,
          key: el.tagName + '|' + (el.innerText||'').slice(0,20) + '|' + Math.round(r.x) + ',' + Math.round(r.y + scrollY)}; }
"""


def spanish_syllables(word: str) -> int:
    w = word.lower()
    w = re.sub(r"[^a-záéíóúüñ]", "", w)
    if not w:
        return 0
    groups = re.findall(r"[aeiouáéíóúü]+", w)
    n = 0
    for g in groups:
        n += 1
        for a, b in zip(g, g[1:]):
            strong = set("aeoáéó")
            if (a in strong and b in strong) or a in "íú" or b in "íú":
                n += 1  # hiato
    return max(n, 1)


def inflesz(blocks: list[str]) -> dict:
    text = " ".join(blocks)
    words = [w for w in re.split(r"\s+", text) if re.search(r"[A-Za-zÁÉÍÓÚáéíóúñÑ]", w)]
    if not words:
        return {"palabras": 0}
    sentences = max(1, len([s for s in re.split(r"[.!?:;]+(?:\s|$)", text) if s.strip()]))
    syl = sum(spanish_syllables(w) for w in words)
    idx = 206.835 - 62.3 * (syl / len(words)) - (len(words) / sentences)
    escala = ("muy difícil" if idx < 40 else "algo difícil" if idx < 55 else "normal" if idx < 65
              else "bastante fácil" if idx < 80 else "muy fácil")
    longest = max(blocks, key=lambda b: len(b.split()))
    return {"palabras_en_prosa": len(words), "oraciones": sentences, "palabras_por_oracion": round(len(words) / sentences, 1),
            "silabas_por_palabra": round(syl / len(words), 2), "inflesz": round(idx, 1), "escala_inflesz": escala,
            "bloque_mas_largo_palabras": len(longest.split()), "bloque_mas_largo_inicio": longest[:90]}


class Evaluacion:
    def __init__(self, args):
        self.args = args
        self.out: Path = args.salida
        self.monitor = Monitor()
        self.tasks: list[dict] = []
        self.screens: dict[str, dict] = {}
        self.nav: dict = {"rutas": ROUTES, "enlaces": [], "atras": [], "deep_link": [], "desconocidas": [],
                          "sin_sesion": [], "estado_activo": {}}
        self.probes: list[dict] = []
        self.keyboard_walks: dict[str, dict] = {}
        self.load_perf: dict[str, dict] = {}
        self.axe_src = Path(args.axe).read_text()
        self.shot_n = 0

    # ---------- capturas y auditorías ----------
    def shot(self, page: Page, name: str, full: bool = True) -> str:
        path = self.out / f"{name}.png"
        page.screenshot(path=str(path), full_page=full)
        return str(path.relative_to(MVP))

    def axe(self, page: Page) -> dict:
        if not page.evaluate("() => !!window.axe"):
            page.add_script_tag(content=self.axe_src)
        res = page.evaluate("""async (tags) => {
            const r = await axe.run(document, {runOnly: {type: 'tag', values: tags}, resultTypes: ['violations']});
            const bp = await axe.run(document, {runOnly: {type: 'tag', values: ['best-practice']}, resultTypes: ['violations']});
            const m = (v) => ({id: v.id, impact: v.impact, tags: v.tags.filter(t => t.startsWith('wcag')), help: v.help,
                               nodos: v.nodes.length, ejemplos: v.nodes.slice(0, 3).map(n => n.target.join(' ') + (n.any[0] && n.any[0].data && n.any[0].data.contrastRatio ? ` (contraste ${n.any[0].data.contrastRatio}:1, requerido ${n.any[0].data.expectedContrastRatio})` : ''))});
            return {wcag: r.violations.map(m), best_practice: bp.violations.map(m)};
        }""", WCAG_TAGS)
        by_impact = {k: 0 for k in ("critical", "serious", "moderate", "minor")}
        nodes_by_impact = dict(by_impact)
        for v in res["wcag"]:
            by_impact[v["impact"] or "minor"] += 1
            nodes_by_impact[v["impact"] or "minor"] += v["nodos"]
        contrast = next((v for v in res["wcag"] if v["id"] == "color-contrast"), None)
        return {"violaciones_por_impacto": by_impact, "nodos_por_impacto": nodes_by_impact,
                "contraste_nodos_fallidos": contrast["nodos"] if contrast else 0, **res}

    def focus_walk(self, page: Page, name: str, max_tabs: int = 80):
        page.evaluate(FOCUS_TOP_JS)
        seq, seen = [], set()
        for _ in range(max_tabs):
            page.keyboard.press("Tab")
            info = page.evaluate(FOCUS_WALK_JS)
            if info is None or info["key"] in seen:
                break
            seen.add(info["key"])
            seq.append({k: v for k, v in info.items() if k != "key"})
        self.keyboard_walks[name] = {
            "paradas_de_foco": len(seq), "sin_foco_visible": [s for s in seq if not s["foco_visible"]],
            "fuera_de_pantalla_al_enfocar": 0,
            "secuencia": seq,
        }
        page.evaluate(FOCUS_TOP_CLEAN_JS)

    def audit(self, page: Page, key: str, titulo: str, wait_ms: int = 300, focus: bool = True):
        """Auditoría de la pantalla en su estado actual, en escritorio y móvil."""
        page.wait_for_timeout(wait_ms)
        entry: dict = {"pantalla": titulo, "ruta": norm_route(page.url)}
        orig = page.viewport_size
        for vp_name, vp in (("desktop", DESKTOP), ("mobile", MOBILE)):
            page.set_viewport_size(vp)
            page.wait_for_timeout(250)
            self.shot_n += 1
            entry[f"captura_{vp_name}"] = self.shot(page, f"{self.shot_n:02d}_{key}_{vp_name}")
            entry[vp_name] = page.evaluate(LAYOUT_JS)
        page.set_viewport_size(DESKTOP)
        page.wait_for_timeout(200)
        entry["axe"] = self.axe(page)
        entry["legibilidad"] = inflesz(page.evaluate(TEXT_JS)["bloques"])
        perf = page.evaluate("() => window.__perf || null")
        entry["cls_en_estado"] = round(perf["cls"], 4) if perf else None
        if focus:
            self.focus_walk(page, key)
        for link in entry["desktop"]["controles"]:
            if link["href"]:
                self.nav["enlaces"].append({"desde": entry["ruta"], "pantalla": key, "texto": link["texto"],
                                            "hacia": norm_route(link["href"])})
        if orig:
            page.set_viewport_size(orig)
        self.screens[key] = entry

    def measure_load(self, ctx: BrowserContext, key: str, url: str, ready: str, reps: int = 3):
        vals = []
        for _ in range(reps):
            p = ctx.new_page()
            p.goto(url, wait_until="load")
            try:
                p.wait_for_selector(ready, timeout=15000)
            except Exception:
                pass
            p.wait_for_timeout(800)
            m = p.evaluate("""() => { const n = performance.getEntriesByType('navigation')[0];
                return {dcl: n.domContentLoadedEventEnd, load: n.loadEventEnd, lcp: window.__perf.lcp, cls: window.__perf.cls,
                        transfer_kb: performance.getEntriesByType('resource').reduce((a, r) => a + (r.transferSize||0), n.transferSize||0) / 1024}; }""")
            m["listo_ms"] = p.evaluate("() => performance.now()")  # referencia
            vals.append(m)
            p.close()
        med = lambda k: round(statistics.median([v[k] for v in vals if v[k] is not None]), 1) if any(v[k] is not None for v in vals) else None
        self.load_perf[key] = {"url": norm_route(url), "repeticiones": reps, "dcl_ms": med("dcl"), "load_ms": med("load"),
                               "lcp_ms": med("lcp"), "cls": round(statistics.median([v["cls"] for v in vals]), 4),
                               "transferido_kb": med("transfer_kb")}

    # ---------- flujo principal ----------
    def run(self, pw, web: str, api: str):
        rng = random.Random(21)
        browser = pw.chromium.launch()
        mk = lambda: browser.new_context(viewport=DESKTOP, locale="es-AR", timezone_id="America/Argentina/Buenos_Aires")
        tctx = mk()
        tctx.add_init_script(PERF_INIT)
        tp = self.monitor.attach(tctx.new_page(), "docente")

        # ===== Login: auditoría + T1 =====
        tp.goto(f"{web}/login")
        tp.wait_for_selector("input[type=email]")
        self.audit(tp, "login", "Login docente")
        tp.fill("input[type=email]", "x@y.z")
        tp.fill("input[type=password]", "malaclave")
        tp.click("button[type=submit]")
        tp.wait_for_selector(".alert-error")
        self.probes.append({"id": "P-login-error", "descripcion": "Login con credenciales inválidas",
                            "mensaje": tp.locator(".alert-error").inner_text(),
                            "foco_tras_error": tp.evaluate("() => document.activeElement.tagName + ' ' + (document.activeElement.type||'')"),
                            "captura": self.shot(tp, "p_login_error", full=False)})
        tp.goto(f"{web}/login")
        tp.wait_for_function("() => document.activeElement && document.activeElement.type === 'email' && !document.activeElement.value")
        with Task(self, "T1", "docente", "Iniciar sesión", minimo=2) as t:
            t.start_at(tp)
            tp.keyboard.type(EMAIL)  # email con autofocus: no requiere clic
            t.click(tp, "input[type=password]")
            tp.keyboard.type(PASSWORD)
            t.click(tp, "button[type=submit]")
            tp.wait_for_url("**/exams")
            t.exito = True
            t.estado = "éxito"
        token = tp.evaluate("() => localStorage.getItem('improntia_token')")

        # Atrás después del login
        tp.go_back()
        tp.wait_for_timeout(600)
        self.nav["atras"].append({"caso": "Atrás inmediatamente después de iniciar sesión", "url_final": norm_route(tp.url),
                                  "muestra_form_login": tp.locator("input[type=password]").count() > 0,
                                  "captura": self.shot(tp, "nav_atras_tras_login", full=False)})
        tp.goto(f"{web}/exams")
        tp.wait_for_selector("h2:text-is('Evaluaciones')")
        self.audit(tp, "evaluaciones_vacio", "Evaluaciones (sin evaluaciones)")

        # ===== T2 crear evaluación con política =====
        with Task(self, "T2", "docente", "Crear evaluación con política (señales + reglas)", minimo=8) as t:
            t.start_at(tp)
            t.click(tp, tp.get_by_role("button", name="+ Nueva evaluación"))
            # Probe: envío vacío
            tp.get_by_role("button", name="Crear evaluación").click()
            msg = tp.evaluate("() => { const i = document.querySelector('form input:invalid'); return i ? i.validationMessage : null; }")
            self.probes.append({"id": "P-crear-vacio", "descripcion": "Enviar el formulario de evaluación vacío",
                                "bloqueado_por_validacion_nativa": msg is not None, "mensaje_navegador": msg,
                                "marca_campos_obligatorios_visible": tp.locator("form >> text=*").count() > 0})
            self.audit(tp, "crear_evaluacion", "Formulario Nueva evaluación", focus=False)
            t.click(tp, "input[placeholder^='ej. Parcial']")
            tp.keyboard.type(EXAM_A["name"])
            areas = tp.locator("form textarea")
            for i, k in enumerate(("info", "rules", "prompt")):
                t.click(tp, areas.nth(i))
                tp.keyboard.insert_text(EXAM_A[k])
            t.check(tp, tp.locator("form label:has-text('Scroll') input"), False)
            t.check(tp, tp.locator("form label:has-text('otras pestañas') input"), True)
            t.click(tp, tp.get_by_role("button", name="Crear evaluación"))
            tp.wait_for_selector(".alert-success")
            join_a = tp.locator(".alert-success .join-code").inner_text().strip()
            t.extra["confirmacion"] = tp.locator(".alert-success").inner_text()
            t.extra["boton_copiar_presente"] = tp.locator(".alert-success button:has-text('Copiar')").count() > 0
            t.extra["enlace_absoluto_presente"] = web in tp.locator(".alert-success").inner_text()
            t.observaciones.append("La confirmación muestra la ruta relativa /exam/CODIGO, sin URL completa ni botón de copiar"
                                   if not t.extra["enlace_absoluto_presente"] else "Muestra URL completa")
            self.audit(tp, "evaluacion_creada", "Evaluación creada (aviso con código)", focus=True)
            t.exito, t.estado = True, "éxito"
        exam_a = next(e for e in api_json(api, "/exams", token)[1] if e["join_code"] == join_a)

        # ===== T3 encontrar el código para compartir (desde el inicio, aviso ya cerrado) =====
        tp.reload()
        tp.wait_for_selector("table")
        with Task(self, "T3", "docente", "Encontrar el código/enlace de la evaluación para compartir", minimo=0) as t:
            t.start_at(tp)
            row = tp.locator(f"tr:has-text('{EXAM_A['name']}') .join-code")
            vis = row.is_visible()
            box = row.bounding_box()
            t.extra["codigo_visible_sin_clics"] = vis
            t.extra["codigo_en_primer_viewport"] = bool(box and box["y"] < DESKTOP["height"])
            t.extra["enlace_para_estudiantes_visible"] = tp.get_by_text(f"/exam/{join_a}").count() > 0
            t.extra["boton_copiar"] = tp.locator("button:has-text('Copiar')").count() > 0
            # Versión 2: el enlace absoluto se copia con un botón en la fila (fuera del conteo de acciones).
            copy_btn = tp.locator(f"tr:has-text('{EXAM_A['name']}') button:has-text('Copiar')")
            if copy_btn.count():
                t.extra["boton_copiar_url"] = copy_btn.first.get_attribute("data-url")
                copy_btn.first.click()
                tp.wait_for_timeout(300)
                t.extra["boton_copiar_feedback"] = tp.locator(f"tr:has-text('{EXAM_A['name']}') [aria-live]").first.inner_text()
                t.extra["enlace_para_estudiantes_visible"] = (
                    t.extra["boton_copiar_url"] == f"{web}/exam/{join_a}" and "Copiado" in t.extra["boton_copiar_feedback"])
                if t.extra["enlace_para_estudiantes_visible"]:
                    t.observaciones.append("La fila ofrece «Copiar enlace» (URL absoluta) con la confirmación «Copiado»")
            if not t.extra["enlace_para_estudiantes_visible"]:
                t.observaciones.append("Fuera del aviso de creación solo se ve el código: el enlace /exam/CODIGO no aparece "
                                       "en la lista ni en la pantalla de la evaluación, y no hay botón de copiar")
            t.exito = vis
            t.estado = "éxito con problemas" if vis and not t.extra["enlace_para_estudiantes_visible"] else ("éxito" if vis else "fallo")
        self.audit(tp, "evaluaciones_lista", "Evaluaciones (lista)")

        # ===== Estudiante E1–E3 =====
        sctx = mk()
        sctx.add_init_script(PERF_INIT)
        sp = self.monitor.attach(sctx.new_page(), "estudiante1")
        with Task(self, "E1", "estudiante", "Ingresar a la evaluación con el código", minimo=1) as t:
            # Variante A: el estudiante solo tiene el código y entra al sitio
            t.goto(sp, f"{web}/")
            t.extra["raiz_lleva_a"] = norm_route(sp.url)
            code_field = "input[placeholder*='código' i], input[name*='code' i]"
            t.extra["hay_campo_para_codigo"] = sp.locator(code_field).count() > 0
            # Versión 2: el login docente ofrece un enlace para estudiantes hacia la pantalla del código.
            student_link = sp.get_by_role("link", name=re.compile("estudiante", re.I))
            t.extra["enlace_para_estudiantes_en_raiz"] = student_link.count() > 0
            if not t.extra["hay_campo_para_codigo"] and t.extra["enlace_para_estudiantes_en_raiz"]:
                t.click(sp, student_link.first)
                sp.wait_for_timeout(300)
                t.extra["hay_campo_para_codigo"] = sp.locator(code_field).count() > 0
            if t.extra["hay_campo_para_codigo"]:
                sp.fill(code_field, join_a.lower())  # tipea el código (en minúsculas, como podría hacerlo)
                t.click(sp, "button[type=submit]")
                try:
                    sp.wait_for_selector("text=Qué se registra", timeout=8000)
                    t.extra["solo_con_codigo_llega_al_consentimiento"] = True
                    t.minimo = 3 if t.extra["enlace_para_estudiantes_en_raiz"] else 2  # abrir + (enlace) + continuar
                    t.observaciones.append(f"Con solo el código: raíz → «¿Sos estudiante?» → código → consentimiento "
                                           f"({t.acciones} acciones). Con el enlace completo basta 1.")
                except Exception:
                    t.extra["solo_con_codigo_llega_al_consentimiento"] = False
                    t.errores.append("El campo de código existe pero no lleva al consentimiento")
            if not t.extra["hay_campo_para_codigo"]:
                t.errores.append("Con solo el código no hay dónde ingresarlo: la raíz lleva al login docente "
                                 f"({t.extra['raiz_lleva_a']})")
                self.shot(sp, "e1_raiz_sin_ingreso_por_codigo", full=False)
            # Variante B: código inexistente
            sp.goto(f"{web}/exam/NOEXISTE")
            sp.wait_for_selector("h1")
            t.extra["codigo_inexistente_mensaje"] = sp.locator(".card").inner_text()
            self.audit(sp, "estudiante_codigo_inexistente", "Estudiante: código no encontrado", focus=False)
            # Variante C: enlace completo
            if t.extra.get("solo_con_codigo_llega_al_consentimiento"):
                sp.goto(f"{web}/exam/{join_a}")  # no cuenta: la tarea ya se completó con el código
            else:
                t.goto(sp, f"{web}/exam/{join_a}")
                t.observaciones.append("Solo funciona con el enlace completo /exam/CODIGO (1 acción: abrirlo)")
            sp.wait_for_selector("text=Qué se registra")
            t.exito = True
            t.estado = "éxito con problemas" if t.errores else "éxito"
        self.audit(sp, "estudiante_consentimiento", "Estudiante: información y consentimiento")

        with Task(self, "E2", "estudiante", "Leer la información y dar el consentimiento", minimo=2) as t:
            t.start_at(sp)
            # probes de error antes del camino feliz
            sp.click("button[type=submit]")
            e_sin_codigo = sp.locator(".alert-error").inner_text() if sp.locator(".alert-error").count() else None
            sp.fill("input[placeholder^='ej. P-017']", "EST-USAB-01")
            sp.click("button[type=submit]")
            e_sin_consent = sp.locator(".alert-error").inner_text() if sp.locator(".alert-error").count() else None
            self.probes.append({"id": "P-consent-errores", "descripcion": "Comenzar sin código y sin consentimiento",
                                "mensaje_sin_codigo": e_sin_codigo, "mensaje_sin_consentimiento": e_sin_consent,
                                "error_arriba_del_formulario": True,
                                "captura": self.shot(sp, "p_consent_error", full=False)})
            consent_box = sp.locator("input[type=checkbox]").bounding_box()
            t.extra["checkbox_consentimiento_px"] = [round(consent_box["width"]), round(consent_box["height"])]
            t.extra["altura_pagina_vs_viewport"] = round(sp.evaluate("document.documentElement.scrollHeight / innerHeight"), 2)
            # camino feliz (no cuenta los dos envíos de prueba)
            t.acciones = 0
            t.check(sp, "input[type=checkbox]")
            t.click(sp, "button[type=submit]")
            sp.wait_for_selector("text=Consigna")
            t.exito, t.estado = True, "éxito"

        with Task(self, "E3", "estudiante", "Escribir la respuesta y entregar", minimo=2) as t:
            t.start_at(sp)
            t.click(sp, "textarea")
            human_type(sp, ANSWER, rng)
            sp.evaluate("""(text) => { const ta = document.querySelector('textarea'); const dt = new DataTransfer();
                dt.setData('text', text); ta.dispatchEvent(new ClipboardEvent('paste', {clipboardData: dt, bubbles: true})); }""", PASTED)
            sp.keyboard.insert_text(PASTED)
            sp.wait_for_selector("text=/sincronizado \\(\\d+ eventos enviados\\)/", timeout=20000)
            self.audit(sp, "estudiante_rindiendo", "Estudiante: consigna y respuesta", focus=True)
            sp.click("textarea")
            t.extra["estado_sincronizacion"] = sp.locator("[data-testid=sync-status]").inner_text()
            t.extra["contador_tiempo_o_palabras"] = sp.locator("text=/minutos|restante|palabras|caracteres/i").count() > 0
            # ¿La respuesta queda guardada en el navegador mientras se escribe? (versión 1: solo en memoria)
            t.extra["guardado_borrador_respuesta"] = sp.evaluate(
                "() => { try { return Object.keys(sessionStorage).some(k => (sessionStorage.getItem(k) || '').includes('clave primaria')); } catch { return false; } }")
            t.click(sp, sp.get_by_role("button", name="Finalizar y entregar"))
            t.extra["pide_confirmacion_antes_de_entregar"] = sp.locator("text=/¿Seguro|Confirmar|¿Entregar/").count() > 0
            if sp.get_by_role("button", name=CONFIRM_SUBMIT).count():
                t.extra["foco_en_confirmacion"] = sp.evaluate("() => (document.activeElement.innerText || '').trim()")
                t.minimo += 1  # el paso de confirmación es parte del camino óptimo
                t.click(sp, sp.get_by_role("button", name=CONFIRM_SUBMIT))
            sp.wait_for_selector("text=El servidor confirmó tu entrega", timeout=30000)
            t.extra["mensaje_final"] = sp.locator(".card").inner_text()
            t.exito, t.estado = True, "éxito"
            if not t.extra["pide_confirmacion_antes_de_entregar"]:
                t.observaciones.append("«Finalizar y entregar» entrega en un clic, sin confirmación")
        self.audit(sp, "estudiante_entregado", "Estudiante: entrega confirmada", focus=False)
        sctx.close()

        # ===== E4: entrega con corte de red =====
        s2 = mk()
        s2.add_init_script(PERF_INIT)
        sp2 = self.monitor.attach(s2.new_page(), "estudiante2")
        sp2.goto(f"{web}/exam/{join_a}")
        sp2.wait_for_selector("text=Qué se registra")
        sp2.keyboard.type("EST-USAB-02")
        sp2.check("input[type=checkbox]")
        sp2.click("button[type=submit]")
        sp2.wait_for_selector("text=Consigna")
        with Task(self, "E4", "estudiante", "Entregar con corte de red (sin conexión → reintento)", minimo=2) as t:
            t.start_at(sp2)
            t.esperados_red = ["POST /sessions/:id/events y /end fallan a propósito mientras el contexto está offline"]
            t.click(sp2, "textarea")
            human_type(sp2, "Respuesta escrita durante un corte de red. ", rng)
            s2.set_offline(True)
            human_type(sp2, "Sigo escribiendo sin conexion. ", rng)
            try:
                sp2.wait_for_selector("text=/sin conexión/", timeout=20000)
                t.extra["mensaje_sin_conexion"] = sp2.locator("[data-testid=sync-status]").inner_text()
                self.shot(sp2, "e4_sin_conexion_escribiendo", full=False)
            except Exception:
                t.extra["mensaje_sin_conexion"] = None
                t.observaciones.append("No apareció el aviso «sin conexión» mientras se escribía (el aviso depende del próximo envío programado)")
            t.extra["aviso_conexion_destacado"] = sp2.locator("[data-testid=sync-status].alert, [role=status], [aria-live]").count() > 0
            t.click(sp2, sp2.get_by_role("button", name="Finalizar y entregar"))
            if sp2.get_by_role("button", name=CONFIRM_SUBMIT).count():
                t.minimo += 1
                t.click(sp2, sp2.get_by_role("button", name=CONFIRM_SUBMIT))
            seen = []
            for _ in range(40):
                txt = sp2.locator("[data-testid=finish-status]").inner_text() if sp2.locator("[data-testid=finish-status]").count() else ""
                if txt and (not seen or seen[-1] != txt):
                    seen.append(txt)
                if sp2.get_by_role("button", name="Reintentar la entrega").count():
                    break
                sp2.wait_for_timeout(500)
            t.extra["mensajes_durante_entrega_offline"] = seen
            t.extra["ofrece_reintentar"] = sp2.get_by_role("button", name="Reintentar la entrega").count() > 0
            t.extra["ofrece_entregar_sin_registros"] = sp2.get_by_role("button", name="Entregar sin esos registros").count() > 0
            t.extra["mensaje_de_error_con_aria_live"] = sp2.locator("[data-testid=finish-status][role=alert], [aria-live]").count() > 0
            self.audit(sp2, "estudiante_entrega_fallida", "Estudiante: entrega no confirmada (sin red)", focus=True)
            s2.set_offline(False)
            sp2.wait_for_timeout(500)
            t.click(sp2, sp2.get_by_role("button", name="Reintentar la entrega"))
            sp2.wait_for_selector("text=El servidor confirmó tu entrega", timeout=30000)
            t.extra["mensaje_final"] = sp2.locator(".card").inner_text()
            t.exito, t.estado = True, "éxito"
        s2.close()

        # ===== Línea base poblacional sintética =====
        subprocess.run([self.args.backend_python, "-m", "scripts.seed_demo", "--api", api, "--join-code", join_a,
                        "--normales", "24", "--atipicas", "1"], cwd=BACKEND, env=self.env, check=True,
                       stdout=subprocess.DEVNULL)

        # ===== T4 sesiones que requieren revisión =====
        tp.goto(f"{web}/exams")
        tp.wait_for_selector("table")
        with Task(self, "T4", "docente", "Localizar las sesiones que requieren revisión", minimo=2) as t:
            t.start_at(tp)
            t.click(tp, tp.locator(f"tr:has-text('{EXAM_A['name']}')").get_by_role("link", name="Ver sesiones →"))
            tp.wait_for_selector("table tbody tr")
            rows = tp.locator("table tbody tr")
            flags = [rows.nth(i).get_attribute("class") == "row-flagged" for i in range(rows.count())]
            t.extra["sesiones_en_lista"] = len(flags)
            t.extra["posiciones_marcadas_sin_filtro"] = [i + 1 for i, f in enumerate(flags) if f]
            first_row = rows.first.bounding_box()
            t.extra["y_primera_fila_px"] = round(first_row["y"]) if first_row else None
            t.extra["tabla_debajo_del_primer_viewport"] = bool(first_row and first_row["y"] > DESKTOP["height"])
            t.extra["ordenable_por_columna"] = tp.locator("th button, th[aria-sort]").count() > 0
            self.audit(tp, "sesiones_lista", "Sesiones de la evaluación (abierta)")
            t.check(tp, FILTER_SEL, True)
            tp.wait_for_timeout(800)
            t.extra["sesiones_filtradas"] = tp.locator("table tbody tr").count()
            t.exito = t.extra["sesiones_filtradas"] > 0
            t.estado = "éxito" if t.exito else "fallo"
            if t.extra["tabla_debajo_del_primer_viewport"]:
                t.observaciones.append(f"La tabla empieza en y={t.extra['y_primera_fila_px']} px: con 1366×768 hay que desplazarse "
                                       "más allá de la política y del cierre para ver la primera sesión")
            if t.extra["posiciones_marcadas_sin_filtro"] and t.extra["posiciones_marcadas_sin_filtro"][0] > 3:
                t.observaciones.append("Sin el filtro, las sesiones marcadas no aparecen primero (orden por inicio)")
        self.audit(tp, "sesiones_filtro", "Sesiones con filtro «requieren revisión»", focus=False)

        # ===== T5 detalle =====
        with Task(self, "T5", "docente", "Abrir el detalle de una sesión y entender los indicadores", minimo=1) as t:
            t.start_at(tp)
            t.click(tp, tp.locator("tr:has-text('EST-USAB-01')").get_by_role("link", name="Ver detalle →"))
            tp.wait_for_selector("text=Indicadores preliminares")
            ind = tp.locator(".indicator-item")
            t.extra["indicadores"] = [ind.nth(i).locator(".indicator-kind").inner_text() for i in range(ind.count())]
            t.extra["evidencia_muestra_nombre_tecnico"] = tp.locator(".indicator-evidence code").count() > 0
            t.extra["textos_evidencia"] = [ind.nth(i).locator(".indicator-evidence").inner_text() for i in range(ind.count())]
            t.extra["contexto_claves_crudas"] = tp.locator(".context-list dt").all_inner_texts()
            t.extra["subtitulo"] = tp.locator(".page-header .muted").first.inner_text()
            t.extra["enlace_volver_a_la_evaluacion"] = tp.locator("a:has-text('←'), a:has-text('Volver')").count() > 0
            t.extra["altura_pagina_en_viewports"] = round(tp.evaluate("document.documentElement.scrollHeight / innerHeight"), 2)
            t.exito = ind.count() > 0
            t.estado = "éxito con problemas" if t.exito and t.extra["evidencia_muestra_nombre_tecnico"] else ("éxito" if t.exito else "fallo")
            if t.extra["evidencia_muestra_nombre_tecnico"]:
                t.observaciones.append("La evidencia muestra el nombre interno de la métrica (p. ej. paste_chars_total) y el umbral sin unidad")
            if "exam" in t.extra["subtitulo"].split(" · ")[0]:
                t.observaciones.append("El tipo de sesión se muestra en inglés y crudo («exam»)")
        self.audit(tp, "sesion_detalle", "Detalle de sesión (abierta)")
        detail_url = tp.url

        # ===== T6 registrar decisión =====
        with Task(self, "T6", "docente", "Registrar una decisión de revisión", minimo=1) as t:
            t.start_at(tp)
            pill_before = tp.locator(".count-pill").count()
            btn = tp.get_by_role("button", name="Requiere validación adicional")
            t.extra["y_boton_decision_px"] = round(btn.bounding_box()["y"] + tp.evaluate("scrollY"))
            t.click(tp, tp.locator(".indicator-item input[type=checkbox]").first)
            t.click(tp, "section.card:has(h3:text-is('Revisión docente')) textarea")
            tp.keyboard.insert_text("Pegado de un bloque largo. Se cita al estudiante para una instancia oral.")
            t.click(tp, btn)
            tp.wait_for_selector("section.card:has(h3:text-is('Revisión docente')) .alert-success")
            t.extra["confirmacion"] = tp.locator("section.card:has(h3:text-is('Revisión docente')) .alert-success").inner_text()
            t.extra["contador_nav_antes"] = pill_before
            tp.wait_for_timeout(500)
            t.extra["contador_nav_despues_sin_navegar"] = tp.locator(".count-pill").count()
            t.extra["confirmacion_visible_sin_scroll"] = tp.locator(".alert-success").last.is_visible()
            t.exito, t.estado = True, "éxito"
            if t.extra["contador_nav_despues_sin_navegar"] == pill_before:
                t.observaciones.append("El contador «Validaciones pendientes» de la barra no se actualiza hasta cambiar de ruta")
            self.shot(tp, "t6_revision_registrada", full=False)
        self.audit(tp, "sesion_detalle_revisada", "Detalle de sesión con historial", focus=False)

        tp.get_by_role("link", name=re.compile("Validaciones pendientes")).click()
        tp.wait_for_selector("tr:has-text('EST-USAB-01')")
        self.audit(tp, "validaciones", "Validaciones pendientes")

        # ===== T7 cerrar y ver análisis poblacional =====
        # El docente llega al detalle desde la lista (camino natural) y desde ahí quiere cerrar la evaluación.
        tp.get_by_role("link", name="Evaluaciones").click()
        tp.locator(f"tr:has-text('{EXAM_A['name']}')").get_by_role("link", name="Ver sesiones →").click()
        tp.wait_for_selector("table tbody tr")
        tp.locator("tr:has-text('EST-USAB-01')").get_by_role("link", name="Ver detalle →").click()
        tp.wait_for_selector("text=Indicadores preliminares")
        with Task(self, "T7", "docente", "Cerrar la evaluación y ver el análisis poblacional", minimo=3) as t:
            t.start_at(tp)
            t.back(tp)  # desde el detalle: no hay enlace de vuelta a la evaluación
            if "/sessions" not in tp.url or "/exams/" not in tp.url:
                t.observaciones.append(f"Atrás desde el detalle llevó a {norm_route(tp.url)}")
                tp.goto(f"{web}/exams/{exam_a['id']}/sessions")
            tp.wait_for_selector("table")
            close_btn = tp.get_by_role("button", name="Cerrar la evaluación y analizar…")
            t.extra["y_boton_cierre_px"] = round(close_btn.bounding_box()["y"])
            t.click(tp, close_btn)
            t.extra["aviso_sesiones_en_curso"] = tp.locator("[data-testid=close-active-warning]").count() > 0
            t.click(tp, tp.get_by_role("button", name="Confirmar el cierre"))
            tp.wait_for_selector("text=Evaluación cerrada el", timeout=60000)
            tp.wait_for_selector("td:text-is('Con marca')", timeout=20000)
            t.extra["sesiones_con_marca_en_tabla"] = tp.locator("td:text-is('Con marca')").count()
            t.extra["resumen_resultado_en_tarjeta_cierre"] = tp.locator("section.card:has(h3:text-is('Análisis poblacional'))").inner_text()
            t.extra["estado_cerrada_en_lista_de_evaluaciones"] = None
            # Se mide si la tarjeta informa el resultado del modelo («El modelo marcó N de M…»).
            t.extra["resultado_visible_en_tarjeta_cierre"] = bool(
                re.search(r"marc[óo] \d+ de \d+", t.extra["resumen_resultado_en_tarjeta_cierre"]))
            t.exito = True
            t.estado = "éxito" if t.extra["resultado_visible_en_tarjeta_cierre"] else "éxito con problemas"
            if not t.extra["resultado_visible_en_tarjeta_cierre"]:
                t.observaciones.append("Tras el cierre la tarjeta solo informa la fecha: el resultado (cuántas sesiones marcó el modelo) "
                                       "hay que buscarlo en la columna «Modelo» o en la pestaña Panorama")
            if t.extra["y_boton_cierre_px"] > DESKTOP["height"]:
                t.observaciones.append(f"«Cerrar la evaluación y analizar…» queda en y={t.extra['y_boton_cierre_px']} px, "
                                       "debajo del primer viewport (1366×768)")
        self.audit(tp, "sesiones_cerrada", "Sesiones de la evaluación (cerrada)", focus=False)
        tp.goto(f"{web}/exams")
        tp.wait_for_selector("table")
        self.tasks[-1]["estado_cerrada_en_lista_de_evaluaciones"] = tp.locator("text=/[Cc]errada/").count() > 0
        tp.goto(f"{web}/exams/{exam_a['id']}/sessions")
        tp.wait_for_selector("table")

        # ===== T8 panorama =====
        with Task(self, "T8", "docente", "Leer el panorama de la evaluación", minimo=1) as t:
            t.start_at(tp)
            t.click(tp, tp.get_by_role("tab", name="Panorama"))
            tp.wait_for_selector("[data-testid=panorama-cobertura]:has-text('sesiones evaluadas')", timeout=20000)
            t.extra["tarjetas"] = tp.locator(".panorama-cards .stat").all_inner_texts()
            t.extra["cobertura"] = tp.locator("[data-testid=panorama-cobertura]").inner_text()
            t.extra["url_refleja_pestana"] = "panorama" in tp.url.lower()
            t.extra["barras_con_texto_alternativo"] = tp.locator(".bar-track[role=img], .bar-track[aria-label]").count() > 0
            t.exito, t.estado = True, "éxito"
            if not t.extra["url_refleja_pestana"]:
                t.observaciones.append("La pestaña no queda en la URL: recargar o compartir el enlace vuelve a «Sesiones»")
        self.audit(tp, "panorama", "Panorama de la evaluación")
        tp.reload()
        tp.wait_for_selector("table")
        self.nav["deep_link"].append({"ruta": "/exams/:id/sessions (pestaña Panorama)", "accion": "recargar",
                                      "mantiene_estado": tp.locator("[role=tab][aria-selected=true]").inner_text() == "Panorama",
                                      "pestana_tras_recargar": tp.locator("[role=tab][aria-selected=true]").inner_text()})
        tp.get_by_role("tab", name="Panorama").click()
        tp.wait_for_timeout(300)
        tp.go_back()
        tp.wait_for_timeout(600)
        self.nav["atras"].append({"caso": "Atrás después de cambiar a la pestaña Panorama", "url_final": norm_route(tp.url),
                                  "esperado": "/exams/:id/sessions (pestaña Sesiones)",
                                  "sale_de_la_evaluacion": "/sessions" not in tp.url})

        # ===== T9 eliminar sesión =====
        sessions_a = api_json(api, f"/sessions?exam_id={exam_a['id']}", token)[1]
        victim = next(s for s in sessions_a if s["participant_id"].startswith("SINT-") and "ATIP" not in s["participant_id"])
        tp.goto(f"{web}/exams/{exam_a['id']}/sessions")
        tp.wait_for_selector("table")
        with Task(self, "T9", "docente", "Eliminar una sesión (RF17)", minimo=3) as t:
            t.start_at(tp)
            t.click(tp, tp.locator(f"tr:has-text('{victim['participant_id']}')").get_by_role("link", name="Ver detalle →"))
            tp.wait_for_selector("text=Eliminar la sesión")
            del_btn = tp.get_by_role("button", name="Eliminar esta sesión…")
            t.extra["y_boton_eliminar_px"] = round(del_btn.bounding_box()["y"] + tp.evaluate("scrollY"))
            t.click(tp, del_btn)
            confirm = tp.get_by_role("button", name="Confirmar la eliminación")
            t.extra["clase_boton_confirmar"] = confirm.get_attribute("class")
            t.extra["clase_boton_validacion_adicional"] = tp.get_by_role("button", name="Requiere validación adicional").get_attribute("class")
            t.click(tp, confirm)
            tp.wait_for_timeout(1500)
            t.extra["url_tras_eliminar"] = norm_route(tp.url)
            t.extra["mensaje_tras_eliminar"] = tp.locator(".alert").all_inner_texts()
            status, _ = api_json(api, f"/sessions/{victim['id']}", token)
            t.extra["sesion_borrada_api_status"] = status
            t.exito = status == 404
            if t.extra["url_tras_eliminar"] != "/exams/:id/sessions":
                t.errores.append(f"Después de eliminar navega a /exams/{{examId}} (ruta inexistente) y el comodín redirige a "
                                 f"{t.extra['url_tras_eliminar']}: se pierde el contexto de la evaluación y no hay confirmación")
            t.estado = "éxito con problemas" if t.exito and t.errores else ("éxito" if t.exito else "fallo")
            self.shot(tp, "t9_tras_eliminar", full=False)

        # ===== Teclado: tareas solo con Tab/Enter/Espacio =====
        self.keyboard_suite(browser, mk, web, api, join_a, exam_a, rng)

        # ===== Navegabilidad =====
        self.navigability(browser, mk, tctx, tp, web, api, token, exam_a)

        # ===== Tiempos de carga por ruta =====
        sessions_a = api_json(api, f"/sessions?exam_id={exam_a['id']}", token)[1]
        est = next(s for s in sessions_a if s["participant_id"] == "EST-USAB-01")
        pctx = mk()
        pctx.add_init_script(PERF_INIT)
        pctx.add_init_script(f"localStorage.setItem('improntia_token', {json.dumps(token)})")
        self.measure_load(pctx, "login", f"{web}/login", "input[type=email]")
        self.measure_load(pctx, "evaluaciones_lista", f"{web}/exams", "table")
        self.measure_load(pctx, "sesiones_cerrada", f"{web}/exams/{exam_a['id']}/sessions", "table")
        self.measure_load(pctx, "sesion_detalle_revisada", f"{web}/sessions/{est['id']}", "text=Indicadores preliminares")
        self.measure_load(pctx, "validaciones", f"{web}/validaciones", "h2")
        pctx.close()
        sctx2 = mk()
        sctx2.add_init_script(PERF_INIT)
        self.measure_load(sctx2, "estudiante_consentimiento_b", f"{web}/exam/{self.join_b}", "text=Qué se registra")
        self.measure_load(sctx2, "estudiante_codigo_inexistente", f"{web}/exam/NOEXISTE", "h1")
        sctx2.close()
        browser.close()

    # ------------------------------------------------------------------------------
    def keyboard_suite(self, browser, mk, web, api, join_a, exam_a, rng):
        is_text = lambda s: f"el => (el.innerText || '').trim().startsWith({json.dumps(s)})"
        kctx = mk()
        kp = self.monitor.attach(kctx.new_page(), "docente-teclado")
        kp.goto(f"{web}/login")
        kp.wait_for_function("() => document.activeElement && document.activeElement.type === 'email'")
        with Task(self, "T1", "docente", "Iniciar sesión", minimo=1, modo="teclado") as t:
            t.start_at(kp, keep_focus=True)
            kp.keyboard.type(EMAIL)
            t.press(kp, "Tab")
            kp.keyboard.type(PASSWORD)
            t.press(kp, "Enter")
            kp.wait_for_url("**/exams")
            t.exito, t.estado = True, "éxito"
        kp.wait_for_selector("table")
        with Task(self, "T2", "docente", "Crear evaluación con política (señales + reglas)", minimo=3, modo="teclado") as t:
            t.start_at(kp)
            t.tab_until(kp, is_text("+ Nueva evaluación"))
            t.press(kp, "Enter")
            t.tab_until(kp, "el => el.tagName === 'INPUT' && (el.placeholder||'').startsWith('ej. Parcial')")
            kp.keyboard.type(EXAM_B["name"])
            for k in ("info", "rules", "prompt"):
                t.press(kp, "Tab")
                kp.keyboard.insert_text(EXAM_B[k])
            t.tab_until(kp, "el => el.type === 'checkbox' && el.parentElement.innerText.includes('Scroll')", max_tabs=10)
            t.press(kp, "Space")
            t.tab_until(kp, is_text("Crear evaluación"), max_tabs=10)
            t.extra["foco_visible_en_boton_crear"] = kp.evaluate(FOCUS_WALK_JS)["foco_visible"]
            t.press(kp, "Enter")
            kp.wait_for_selector(".alert-success")
            self.join_b = kp.locator(".alert-success .join-code").inner_text().strip()
            t.exito, t.estado = True, "éxito"
        token = kp.evaluate("() => localStorage.getItem('improntia_token')")
        exam_b = next(e for e in api_json(api, "/exams", token)[1] if e["join_code"] == self.join_b)

        # Estudiante por teclado en B
        ks = mk()
        ksp = self.monitor.attach(ks.new_page(), "estudiante-teclado")
        ksp.goto(f"{web}/exam/{self.join_b}")
        ksp.wait_for_selector("text=Qué se registra")
        with Task(self, "E2", "estudiante", "Leer la información y dar el consentimiento", minimo=2, modo="teclado") as t:
            t.start_at(ksp, keep_focus=True)
            ksp.keyboard.type("EST-TECLADO-01")
            t.tab_until(ksp, "el => el.type === 'checkbox'", max_tabs=10)
            t.extra["foco_visible_checkbox"] = ksp.evaluate(FOCUS_WALK_JS)["foco_visible"]
            t.press(ksp, "Space")
            t.press(ksp, "Tab")
            t.press(ksp, "Enter")
            ksp.wait_for_selector("text=Consigna")
            t.exito, t.estado = True, "éxito"
        with Task(self, "E3", "estudiante", "Escribir la respuesta y entregar", minimo=1, modo="teclado") as t:
            t.start_at(ksp)
            t.tab_until(ksp, "el => el.tagName === 'TEXTAREA'", max_tabs=10)
            human_type(ksp, "Normalizar es quitar redundancia. ", rng)
            t.press(ksp, "Tab")
            t.extra["foco_en"] = ksp.evaluate(FOCUS_WALK_JS)
            t.press(ksp, "Enter")
            ksp.wait_for_timeout(200)
            if ksp.get_by_role("button", name=CONFIRM_SUBMIT).count():
                # La confirmación enfoca «Sí, entregar»: basta otro Enter.
                t.extra["foco_en_confirmacion"] = ksp.evaluate("() => (document.activeElement.innerText || '').trim()")
                t.minimo += 1
                t.press(ksp, "Enter")
            ksp.wait_for_selector("text=El servidor confirmó tu entrega", timeout=30000)
            t.extra["foco_tras_entrega"] = ksp.evaluate("() => document.activeElement.tagName")
            t.exito, t.estado = True, "éxito"
        ks.close()

        # Probes: recargar y Atrás en medio del examen (examen B)
        pr = mk()
        prp = self.monitor.attach(pr.new_page(), "estudiante-probe")
        prp.goto(f"{web}/exam/{self.join_b}")
        prp.wait_for_selector("text=Qué se registra")
        prp.keyboard.type("EST-RECARGA-01")
        prp.check("input[type=checkbox]")
        prp.click("button[type=submit]")
        prp.wait_for_selector("text=Consigna")
        prp.click("textarea")
        prp.keyboard.type("Texto que el estudiante ya habia escrito.")
        t_reload = time.perf_counter()
        prp.reload()
        prp.wait_for_timeout(1500)
        after_reload = {"vuelve_a_consentimiento": prp.locator("text=Qué se registra").count() > 0,
                        "respuesta_conservada": prp.locator("textarea").count() > 0 and "ya habia" in (prp.locator("textarea").input_value() if prp.locator("textarea").count() else ""),
                        "aviso_beforeunload": any(d["type"] == "beforeunload" for d in self.monitor.dialogs_since(t_reload, "estudiante-probe"))}
        if after_reload["vuelve_a_consentimiento"]:
            prp.keyboard.type("EST-RECARGA-01")
            prp.check("input[type=checkbox]")
            prp.click("button[type=submit]")
            prp.wait_for_timeout(1500)
            after_reload["reingreso_mismo_codigo"] = ("permitido: crea otra sesión" if prp.locator("text=Consigna").count()
                                                      else prp.locator(".alert-error").inner_text() if prp.locator(".alert-error").count() else "?")
        else:
            after_reload["reingreso_mismo_codigo"] = ("no hace falta: retoma la misma sesión" if prp.locator("text=Consigna").count()
                                                      else "?")
        sess_b = api_json(api, f"/sessions?exam_id={exam_b['id']}", token)[1]
        after_reload["sesiones_de_ese_codigo"] = len([s for s in sess_b if s["participant_id"] == "EST-RECARGA-01"])
        after_reload["captura"] = self.shot(prp, "p_recarga_durante_examen", full=False)
        self.probes.append({"id": "P-recarga-examen", "descripcion": "Recargar la página con el examen en curso", **after_reload})
        self.nav["deep_link"].append({"ruta": "/exam/:joinCode (examen en curso)", "accion": "recargar",
                                      "mantiene_estado": after_reload["respuesta_conservada"],
                                      "detalle": "vuelve a la pantalla de consentimiento; la respuesta escrita se pierde"
                                      if not after_reload["respuesta_conservada"] else "conserva"})
        prp.click("textarea") if prp.locator("textarea").count() else None
        prp.keyboard.type("Otro texto.")
        t_leave = time.perf_counter()
        prp.goto("about:blank")
        prp.go_back()
        prp.wait_for_timeout(1500)
        self.nav["atras"].append({"caso": "Estudiante sale de la página en medio del examen y vuelve con Atrás",
                                  "url_final": norm_route(prp.url),
                                  "vuelve_a_consentimiento": prp.locator("text=Qué se registra").count() > 0,
                                  "respuesta_conservada": prp.locator("textarea").count() > 0 and "Otro texto" in (prp.locator("textarea").input_value() if prp.locator("textarea").count() else ""),
                                  "advertencia_al_salir": any(d["type"] == "beforeunload" for d in self.monitor.dialogs_since(t_leave, "estudiante-probe"))})
        sess_b = api_json(api, f"/sessions?exam_id={exam_b['id']}", token)[1]
        self.nav["atras"][-1]["sesiones_de_ese_codigo"] = len([s for s in sess_b if s["participant_id"] == "EST-RECARGA-01"])
        pr.close()

        # Docente por teclado sobre la evaluación A
        kp.goto(f"{web}/exams")
        kp.wait_for_selector("table")
        with Task(self, "T4", "docente", "Localizar las sesiones que requieren revisión", minimo=2, modo="teclado") as t:
            t.start_at(kp)
            t.tab_until(kp, f"el => el.tagName === 'A' && el.closest('tr') && el.closest('tr').innerText.includes({json.dumps(EXAM_A['name'])})")
            t.press(kp, "Enter")
            kp.wait_for_selector("table tbody tr")
            n = t.tab_until(kp, "el => el.type === 'checkbox' && el.closest('.page-header, .toolbar')", max_tabs=30)
            t.press(kp, "Space")
            kp.wait_for_timeout(600)
            t.exito = n is not None and kp.locator("table tbody tr").count() > 0
            t.estado = "éxito" if t.exito else "fallo"
        with Task(self, "T5", "docente", "Abrir el detalle de una sesión y entender los indicadores", minimo=1, modo="teclado") as t:
            t.start_at(kp)
            t.tab_until(kp, "el => el.tagName === 'A' && el.closest('tr') && el.closest('tr').innerText.includes('EST-USAB-01')", max_tabs=60)
            t.press(kp, "Enter")
            kp.wait_for_selector("text=Indicadores preliminares")
            t.exito, t.estado = True, "éxito"
        with Task(self, "T6", "docente", "Registrar una decisión de revisión", minimo=1, modo="teclado") as t:
            t.start_at(kp)
            n = t.tab_until(kp, is_text("Marcar como revisada"), max_tabs=60)
            t.extra["tabs_hasta_la_decision"] = n
            t.extra["foco_visible"] = kp.evaluate(FOCUS_WALK_JS)["foco_visible"]
            t.press(kp, "Enter")
            kp.wait_for_selector(".review-history li:nth-child(2)")
            t.exito, t.estado = True, "éxito"
        with Task(self, "T8", "docente", "Leer el panorama de la evaluación", minimo=1, modo="teclado") as t:
            kp.goto(f"{web}/exams/{exam_a['id']}/sessions")
            kp.wait_for_selector("table")
            t.start_at(kp)
            t.tab_until(kp, "el => el.getAttribute('role') === 'tab' && el.innerText.trim() === 'Panorama'", max_tabs=40)
            t.extra["flechas_entre_pestanas"] = None
            t.press(kp, "Enter")
            kp.wait_for_selector("[data-testid=panorama-cobertura]", timeout=15000)
            t.press(kp, "Shift+Tab")
            t.press(kp, "ArrowRight")
            t.extra["flechas_entre_pestanas"] = kp.evaluate("() => document.activeElement.innerText.trim()") == "Panorama"
            t.acciones -= 1  # la prueba de flecha no es parte del camino
            t.exito, t.estado = True, "éxito"
        with Task(self, "T9", "docente", "Eliminar una sesión (RF17), desde el detalle", minimo=2, modo="teclado") as t:
            sessions_a = api_json(api, f"/sessions?exam_id={exam_a['id']}", token)[1]
            victim = [s for s in sessions_a if s["participant_id"].startswith("SINT-0")][-1]
            kp.goto(f"{web}/sessions/{victim['id']}")
            kp.wait_for_selector("text=Eliminar la sesión")
            t.start_at(kp)
            t.tab_until(kp, is_text("Eliminar esta sesión"), max_tabs=60)
            t.press(kp, "Enter")
            t.extra["foco_tras_abrir_confirmacion"] = kp.evaluate("() => document.activeElement === document.body ? 'BODY' : (document.activeElement.innerText || document.activeElement.tagName).trim()")
            t.tab_until(kp, is_text("Confirmar la eliminación"), max_tabs=4, report=False) or t.tab_until(kp, is_text("Confirmar la eliminación"), max_tabs=8, shift=True)
            t.press(kp, "Enter")
            kp.wait_for_timeout(1500)
            t.exito = api_json(api, f"/sessions/{victim['id']}", token)[0] == 404
            foco_perdido = t.extra["foco_tras_abrir_confirmacion"] in ("BODY", "")
            t.estado = ("éxito con problemas" if foco_perdido else "éxito") if t.exito else "fallo"
            if foco_perdido:
                t.observaciones.append("Al abrir la confirmación el foco se pierde (el botón enfocado desaparece)")
        with Task(self, "T7", "docente", "Cerrar la evaluación (desde la pantalla de la evaluación)", minimo=2, modo="teclado") as t:
            kp.goto(f"{web}/exams/{exam_b['id']}/sessions")
            kp.wait_for_selector("text=Análisis poblacional")
            t.start_at(kp)
            t.tab_until(kp, is_text("Cerrar la evaluación y analizar"), max_tabs=30)
            t.press(kp, "Enter")
            t.extra["foco_tras_abrir_confirmacion"] = kp.evaluate("() => document.activeElement === document.body ? 'BODY' : (document.activeElement.innerText || document.activeElement.tagName).trim()")
            t.extra["aviso_sesiones_en_curso"] = kp.locator("[data-testid=close-active-warning]").inner_text() if kp.locator("[data-testid=close-active-warning]").count() else None
            t.tab_until(kp, is_text("Confirmar el cierre"), max_tabs=4, report=False) or t.tab_until(kp, is_text("Confirmar el cierre"), max_tabs=8, shift=True)
            t.press(kp, "Enter")
            kp.wait_for_selector("text=Evaluación cerrada el", timeout=60000)
            t.exito, t.estado = True, "éxito"
        kctx.close()

    # ------------------------------------------------------------------------------
    def navigability(self, browser, mk, tctx, tp, web, api, token, exam_a):
        sessions_a = api_json(api, f"/sessions?exam_id={exam_a['id']}", token)[1]
        est = next(s for s in sessions_a if s["participant_id"] == "EST-USAB-01")
        # Atrás: inicio → sesiones → detalle → atrás → atrás
        tp.goto(f"{web}/exams")
        tp.wait_for_selector("table")
        tp.locator(f"tr:has-text('{EXAM_A['name']}')").get_by_role("link", name="Ver sesiones →").click()
        tp.wait_for_url("**/sessions*")
        tp.wait_for_selector("table tbody tr")
        # El filtro vive en la URL (?revision=1): el estado de la casilla se confirma después de
        # la navegación, no en el mismo instante del clic (Page.check lo daba por no cambiado).
        tp.locator(FILTER_SEL).click()
        tp.wait_for_function(f"() => document.querySelector({json.dumps(FILTER_SEL)})?.checked === true", timeout=5000)
        tp.wait_for_timeout(500)
        tp.locator("tr:has-text('EST-USAB-01')").get_by_role("link", name="Ver detalle →").click()
        tp.wait_for_selector("text=Indicadores preliminares")
        tp.go_back()
        tp.wait_for_selector("table")
        r1 = norm_route(tp.url)
        filtro = tp.locator(FILTER_SEL).is_checked()
        tp.go_back()
        tp.wait_for_timeout(500)
        self.nav["atras"].append({"caso": "Inicio → Sesiones (con filtro) → Detalle → Atrás → Atrás",
                                  "primer_atras": r1, "conserva_filtro": filtro, "segundo_atras": norm_route(tp.url)})
        # Estado activo de la navegación superior por ruta
        for key, url in (("/exams", f"{web}/exams"), ("/exams/:id/sessions", f"{web}/exams/{exam_a['id']}/sessions"),
                         ("/sessions/:id", f"{web}/sessions/{est['id']}"), ("/validaciones", f"{web}/validaciones")):
            tp.goto(url)
            tp.wait_for_timeout(900)
            self.nav["estado_activo"][key] = {"nav": tp.evaluate("() => [...document.querySelectorAll('.topnav a')].filter(a => a.classList.contains('active')).map(a => a.innerText.trim())"),
                                              "titulo_documento": tp.title(),
                                              "migas": tp.locator("nav[aria-label*=breadcrumb i], .breadcrumb").count(),
                                              "enlace_volver": tp.locator("a:has-text('←'), a:has-text('Volver')").count()}
        # Deep-link + recarga autenticado
        cases = [("/exams", f"{web}/exams", "h2:text-is('Evaluaciones')"),
                 ("/", f"{web}/", "h2:text-is('Evaluaciones')"),
                 ("/exams/:id/sessions", f"{web}/exams/{exam_a['id']}/sessions", "table"),
                 ("/sessions/:id", f"{web}/sessions/{est['id']}", "text=Indicadores preliminares"),
                 ("/validaciones", f"{web}/validaciones", "h2"),
                 ("/login (con sesión iniciada)", f"{web}/login", "body"),
                 ("/exam/:joinCode", f"{web}/exam/{self.join_b}", "h1")]
        for name, url, sel in cases:
            p = tctx.new_page()
            self.monitor.attach(p, "deeplink")
            p.goto(url)
            ok1 = True
            try:
                p.wait_for_selector(sel, timeout=8000)
            except Exception:
                ok1 = False
            p.reload()
            ok2 = True
            try:
                p.wait_for_selector(sel, timeout=8000)
            except Exception:
                ok2 = False
            self.nav["deep_link"].append({"ruta": name, "accion": "abrir enlace directo + recargar", "carga": ok1,
                                          "tras_recargar": ok2, "url_final": norm_route(p.url),
                                          "observacion": ("muestra el formulario de login aunque hay sesión iniciada"
                                                          if name.startswith("/login") and p.locator("input[type=password]").count() else "")})
            p.close()
        # Rutas desconocidas / recursos inexistentes
        fake = "00000000-0000-4000-8000-000000000000"
        anon = mk()
        for name, url, ctx in (("/ruta-inexistente (con sesión)", f"{web}/ruta-inexistente", tctx),
                               ("/ruta-inexistente (sin sesión)", f"{web}/ruta-inexistente", anon),
                               ("/exams/{inexistente}/sessions", f"{web}/exams/{fake}/sessions", tctx),
                               ("/sessions/{inexistente}", f"{web}/sessions/{fake}", tctx),
                               ("/exam/NOEXISTE (estudiante)", f"{web}/exam/NOEXISTE", anon),
                               ("/exam (estudiante, sin código)", f"{web}/exam", anon)):
            p = ctx.new_page()
            p.goto(url)
            p.wait_for_timeout(1500)
            body = p.locator("main, .centered-page, body").first.inner_text()[:220].replace("\n", " · ")
            shot = self.shot(p, "nav_404_" + re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_"), full=False)
            self.nav["desconocidas"].append({"ruta": name, "url_final": norm_route(p.url), "texto_visible": body,
                                             "mensaje_explicito": bool(re.search(r"no (se )?encontr|no existe|no se pudo", body, re.I)),
                                             "captura": shot})
            p.close()
        anon.close()
        # Sin sesión: deep link a un detalle y vuelta tras login
        uctx = mk()
        up = uctx.new_page()
        up.goto(f"{web}/sessions/{est['id']}")
        up.wait_for_timeout(800)
        r_login = norm_route(up.url)
        up.fill("input[type=email]", EMAIL)
        up.fill("input[type=password]", PASSWORD)
        up.click("button[type=submit]")
        up.wait_for_timeout(1500)
        self.nav["sin_sesion"].append({"caso": "Enlace directo a /sessions/:id sin sesión iniciada", "redirige_a": r_login,
                                       "tras_login_vuelve_al_enlace": "/sessions/" in up.url, "url_tras_login": norm_route(up.url)})
        # Token vencido/ inválido
        up.evaluate("() => localStorage.setItem('improntia_token', 'token-invalido')")
        up.goto(f"{web}/exams")
        up.wait_for_timeout(1500)
        self.nav["sin_sesion"].append({"caso": "Token inválido o vencido en /exams", "url_final": norm_route(up.url),
                                       "mensaje": up.locator(".alert, .muted").first.inner_text() if up.locator(".alert, .muted").count() else None,
                                       "redirige_a_login": "/login" in up.url,
                                       "captura": self.shot(up, "nav_token_invalido", full=False)})
        uctx.close()

    # ------------------------------------------------------------------------------
    def summary(self) -> dict:
        axe_tot = {k: 0 for k in ("critical", "serious", "moderate", "minor")}
        nodes_tot = dict(axe_tot)
        rules: dict[str, dict] = {}
        for k, s in self.screens.items():
            for imp, n in s["axe"]["violaciones_por_impacto"].items():
                axe_tot[imp] += n
            for imp, n in s["axe"]["nodos_por_impacto"].items():
                nodes_tot[imp] += n
            for v in s["axe"]["wcag"]:
                r = rules.setdefault(v["id"], {"impacto": v["impact"], "wcag": v["tags"], "ayuda": v["help"], "pantallas": [], "nodos": 0})
                r["pantallas"].append(k)
                r["nodos"] += v["nodos"]
        # Profundidad (BFS sobre los enlaces observados; la pestaña Panorama suma 1 clic a Sesiones)
        graph: dict[str, set] = {}
        for e in self.nav["enlaces"]:
            graph.setdefault(e["desde"], set()).add(e["hacia"])
        depth = {"/exams": 0}
        frontier = ["/exams"]
        while frontier:
            nxt = []
            for n in frontier:
                for m in graph.get(n, ()):
                    if m not in depth:
                        depth[m] = depth[n] + 1
                        nxt.append(m)
            frontier = nxt
        if "/exams/:id/sessions" in depth:
            depth["/exams/:id/sessions#panorama"] = depth["/exams/:id/sessions"] + 1
        # Terminología: textos de controles por pantalla
        inventory: dict[str, set] = {}
        for k, s in self.screens.items():
            for c in s["desktop"]["controles"]:
                if c["texto"]:
                    inventory.setdefault(c["texto"], set()).add(f"{k}:{c['clase']}")
        cerrar = sorted(t for t in inventory if re.match(r"(?i)cerrar", t))
        lower = sorted(t for t in inventory if t[:1].islower())
        return {"axe_violaciones_por_impacto": axe_tot, "axe_nodos_por_impacto": nodes_tot, "axe_reglas": rules,
                "profundidad_desde_inicio": depth,
                "terminologia": {"controles": {t: sorted(v) for t, v in sorted(inventory.items())},
                                 "usos_de_cerrar": cerrar, "controles_en_minuscula": lower}}

    def save(self):
        data = {
            "tipo": "Evaluación experta y automatizada de usabilidad y navegabilidad (inspección heurística + recorridos "
                    "instrumentados). No es una prueba con usuarios: no hay participantes ni SUS; los tiempos son de la automatización.",
            "fecha": time.strftime("%Y-%m-%d %H:%M"),
            "entorno": {"navegador": "Chromium (Playwright)", "escritorio": DESKTOP, "movil": MOBILE,
                        "backend": "FastAPI + SQLite temporal", "dashboard": "vite preview (build de producción)",
                        "axe_tags": WCAG_TAGS},
            "tareas": self.tasks, "navegabilidad": self.nav, "pantallas": self.screens, "carga": self.load_perf,
            "teclado_recorridos_de_foco": self.keyboard_walks, "pruebas_de_error": self.probes, "resumen": self.summary(),
        }
        (self.out / "metricas.json").write_text(json.dumps(data, ensure_ascii=False, indent=1, default=list))
        return data


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--backend-python", default=sys.executable)
    ap.add_argument("--api-port", type=int, default=8100)
    ap.add_argument("--web-port", type=int, default=5180)
    ap.add_argument("--axe", default=os.environ.get("AXE_CORE_JS", ""), help="ruta a axe.min.js (axe-core)")
    ap.add_argument("--salida", type=Path, default=OUT_DEFAULT)
    ap.add_argument("--tmp", type=Path, default=None, help="carpeta temporal (base SQLite, build, logs)")
    args = ap.parse_args(argv)
    args.backend_python = resolve_python(args.backend_python)
    if not args.axe or not Path(args.axe).exists():
        ap.error("falta --axe (ruta a axe-core/axe.min.js; instalarlo con npm en una carpeta fuera del repo)")
    args.salida.mkdir(parents=True, exist_ok=True)
    for old in args.salida.glob("*.png"):
        old.unlink()
    tmp = args.tmp or Path(tempfile.mkdtemp(prefix="improntia-usab-"))
    tmp.mkdir(parents=True, exist_ok=True)
    db = tmp / "usabilidad.db"
    if db.exists():
        db.unlink()
    api = f"http://127.0.0.1:{args.api_port}"
    web = f"http://localhost:{args.web_port}"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db}", "VITE_API_URL": f"http://localhost:{args.api_port}",
           "CORS_ORIGINS": web}
    procs: list[subprocess.Popen] = []
    log = open(tmp / "servidores.log", "w")
    try:
        procs.append(subprocess.Popen([args.backend_python, "-m", "uvicorn", "app.main:app", "--port", str(args.api_port)],
                                      cwd=BACKEND, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True))
        wait_http(f"{api}/health")
        subprocess.run([args.backend_python, "-m", "scripts.seed_teacher", EMAIL, PASSWORD], cwd=BACKEND, env=env,
                       check=True, stdout=subprocess.DEVNULL)
        dist = tmp / "dist"
        subprocess.run(["npx", "vite", "build", "--outDir", str(dist), "--emptyOutDir"], cwd=DASHBOARD, env=env, check=True,
                       stdout=log, stderr=subprocess.STDOUT)
        procs.append(subprocess.Popen(["npx", "vite", "preview", "--outDir", str(dist), "--port", str(args.web_port), "--strictPort"],
                                      cwd=DASHBOARD, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True))
        wait_http(web)
        ev = Evaluacion(args)
        ev.env = env
        with sync_playwright() as pw:
            ev.run(pw, web, api)
        data = ev.save()
        ok = sum(1 for t in data["tareas"] if t["exito"])
        print(f"\n{ok}/{len(data['tareas'])} tareas completadas · axe (reglas WCAG por pantalla): "
              f"{data['resumen']['axe_violaciones_por_impacto']} · salida en {args.salida}")
        return 0
    finally:
        # npx no reenvía la señal a vite: se termina el grupo de procesos completo.
        for p in procs:
            try:
                os.killpg(p.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        for p in procs:
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(p.pid, signal.SIGKILL)
        log.close()
        print(f"(logs de servidores: {tmp / 'servidores.log'})")


if __name__ == "__main__":
    raise SystemExit(main())
