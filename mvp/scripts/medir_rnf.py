"""
Medición de los requisitos no funcionales de rendimiento (RNF07, RNF09, RNF11) sobre el
sistema REAL: backend FastAPI levantado con uvicorn (un proceso, como en el Dockerfile),
base SQLite o PostgreSQL, y el dashboard compilado en Chromium (Playwright).

Qué mide (cada prueba se elige con --pruebas):

- rnf11  Tiempo de procesamiento por sesión: latencia de POST /sessions/{id}/end, que
         devuelve recién cuando las métricas e indicadores (reglas) quedaron guardados
         (`procesada = true`); cota 5 s. Se cargan --sesiones sesiones sintéticas
         finalizadas (generador de app/evaluation/synthetic.py, el mismo de
         scripts/evaluar.py y seed_demo.py, con `dwell` emparejado como la captura real)
         en una evaluación; se mide además un barrido por tamaño de sesión
         (--barrido, en múltiplos de una sesión sintética). Con la evaluación completa:
         tiempo del cierre (POST /exams/{id}/cerrar: Isolation Forest sobre la cohorte) y
         consultas docentes (listado, detalle, panorama; cota 2 s), --repeticiones veces.
- rnf09  --concurrentes sesiones activas a la vez, cada una enviando un lote cada 5 s
         (intervalo de syncQueue.ts) con los eventos sintéticos de esa ventana, durante
         --duracion-carga s; en paralelo, un docente repite las consultas de RNF11 sobre la
         evaluación de 500 sesiones. Al final las sesiones se entregan todas a la vez
         (ráfaga de /end, el caso del horario límite). Requiere rnf11 en la misma corrida.
- rnf07  Costo por evento de la captura en el navegador (capture.ts + keyPairing.ts): se
         compila una COPIA del dashboard (no toca dashboard/), se abre la página del
         examen y un script de inicio envuelve los listeners de document/window de los
         tipos que registra capture.ts con performance.now(); se teclea con ritmo humano y
         se mueve el mouse. También se registran las tareas largas (PerformanceObserver
         `longtask`, > 50 ms). Se repite con la CPU ralentizada x4 (CDP), como equipo lento.

Los tiempos de RNF09/RNF11 se miden del lado del cliente HTTP (incluyen red local y
serialización). Cliente y servidor comparten la misma máquina.

Uso (desde mvp/; el intérprete necesita las dependencias del backend + httpx + playwright):

    python scripts/medir_rnf.py --etiqueta sqlite
    python scripts/medir_rnf.py --etiqueta postgres --db-url postgresql://u:p@localhost/db --pruebas rnf11,rnf09
    python scripts/medir_rnf.py --informe docs/evaluacion/rnf_mediciones_sqlite.json \\
        docs/evaluacion/rnf_mediciones_postgres.json

La primera forma escribe docs/evaluacion/rnf_mediciones_<etiqueta>.json con las muestras
crudas; --informe genera docs/evaluacion/rnf_mediciones.md a partir de uno o más JSON.
Con --db-url de PostgreSQL la base se VACÍA al empezar (DROP SCHEMA public CASCADE).
"""
import argparse
import json
import os
import platform
import random
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import httpx
import numpy as np

MVP = Path(__file__).resolve().parent.parent
BACKEND = MVP / "backend"
DASHBOARD = MVP / "dashboard"
OUT_DIR = MVP / "docs" / "evaluacion"
sys.path.insert(0, str(BACKEND))

from app.evaluation.synthetic import SyntheticParams, generate_session  # noqa: E402

EMAIL, PASSWORD = "rnf-medicion@uade.edu.ar", "rnf-clave-123"
SIGNALS = ["keyboard", "mouse", "visibility", "clipboard", "scroll"]
BATCH_INTERVAL_S = 5.0  # = dashboard/src/syncQueue.ts DEFAULT_SYNC_CONFIG.baseDelayMs
LOAD_BATCH = 1000  # tamaño de lote al CARGAR sesiones (la carga no se mide; el máximo del backend es 5000)
BOUNDS = {"rnf11_proc_s": 5.0, "rnf11_query_s": 2.0, "rnf07_event_ms": 50.0}


# ---------------------------------------------------------------- utilidades

def stats(xs: list[float]) -> dict:
    if not xs:
        return {"n": 0}
    a = np.asarray(xs, dtype=float)
    return {"n": int(a.size), "p50": float(np.percentile(a, 50)), "p95": float(np.percentile(a, 95)),
            "max": float(a.max()), "mean": float(a.mean())}


def wait_http(url: str, timeout: float = 90.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status < 500:
                    return
        except Exception:
            time.sleep(0.3)
    raise RuntimeError(f"No respondió {url} en {timeout}s")


def with_dwell(events: list[dict]) -> list[dict]:
    """Agrega `dwell` a cada keyup como lo envía capture.ts desde el Incremento 16 (el
    generador nunca solapa teclas: la pulsación es la keydown inmediatamente anterior)."""
    last_down = None
    out = []
    for e in events:
        e = dict(e)
        if e["type"] == "keydown":
            last_down = e["t"]
        elif e["type"] == "keyup":
            e["dwell"] = round(e["t"] - last_down, 1) if last_down is not None else None
            last_down = None
        out.append(e)
    return out


def synthetic_events(rng: np.random.Generator, params: SyntheticParams, factor: int = 1, profile: str = "normal") -> list[dict]:
    """Una sesión sintética; con factor > 1, `factor` sesiones encadenadas en el tiempo
    (mismo participante no garantizado: solo interesa el volumen)."""
    events, offset = [], 0.0
    for _ in range(factor):
        part = with_dwell(generate_session(rng, params, profile))
        for e in part:
            e["t"] = round(e["t"] + offset, 1)
        events += part
        offset = events[-1]["t"] + 1000.0 if events else 0.0
    return events


def environment(db_url: str) -> dict:
    mem_kb = 0
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal"):
                mem_kb = int(line.split()[1])
    except OSError:
        pass
    cpu_model = ""
    try:
        cpu_model = next((ln.split(":", 1)[1].strip() for ln in Path("/proc/cpuinfo").read_text().splitlines()
                          if ln.startswith("model name")), "")
    except OSError:
        pass
    env = {"cpus": os.cpu_count(), "cpu_model": cpu_model or platform.processor(), "ram_gb": round(mem_kb / 1024 / 1024, 1),
           "os": platform.platform(), "python": platform.python_version(), "motor": "sqlite" if db_url.startswith("sqlite") else "postgresql"}
    if env["motor"] == "sqlite":
        env["motor_version"] = sqlite3.sqlite_version
    else:
        from sqlalchemy import create_engine, text
        from app.config import normalize_database_url
        eng = create_engine(normalize_database_url(db_url))
        with eng.connect() as c:
            env["motor_version"] = c.execute(text("SHOW server_version")).scalar()
        eng.dispose()
    return env


def reset_postgres(db_url: str) -> None:
    from sqlalchemy import create_engine, text
    from app.config import normalize_database_url
    eng = create_engine(normalize_database_url(db_url))
    with eng.begin() as c:
        c.execute(text("DROP SCHEMA public CASCADE"))
        c.execute(text("CREATE SCHEMA public"))
    eng.dispose()


class Backend:
    def __init__(self, python: str, db_url: str, port: int, cors: str):
        self.url = f"http://127.0.0.1:{port}"
        env = {**os.environ, "DATABASE_URL": db_url, "SEED_TEACHERS": f"{EMAIL}:{PASSWORD}", "CORS_ORIGINS": cors}
        env.pop("IMPRONTIA_ENV", None)
        self.log = tempfile.NamedTemporaryFile(prefix="rnf_uvicorn_", suffix=".log", delete=False)
        self.proc = subprocess.Popen(
            [python, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port),
             "--log-level", "warning", "--no-access-log"],
            cwd=BACKEND, env=env, stdout=self.log, stderr=subprocess.STDOUT)
        wait_http(self.url + "/health")

    def stop(self):
        self.proc.terminate()
        try:
            self.proc.wait(10)
        except subprocess.TimeoutExpired:
            self.proc.kill()


def login(api: str) -> str:
    r = httpx.post(f"{api}/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=30)
    r.raise_for_status()
    return r.json()["access_token"]


def create_exam(c: httpx.Client, token: str, name: str) -> dict:
    r = c.post("/exams", headers={"Authorization": f"Bearer {token}"}, json={
        "name": name, "prompt_text": "Consigna de medición.", "info_text": "Medición automatizada (sintética).",
        "rules_text": "-", "allowed_signals": SIGNALS})
    r.raise_for_status()
    return r.json()


def start(c: httpx.Client, join_code: str, pid: str) -> tuple[str, dict]:
    r = c.post("/sessions/start", json={"exam_code": join_code, "participant_id": pid, "consent_given": True,
                                        "context": {"origen": "medicion_rnf"}})
    r.raise_for_status()
    s = r.json()
    return s["session_id"], {"X-Session-Token": s["session_token"]}


def load_and_end(c: httpx.Client, join_code: str, pid: str, events: list[dict]) -> dict:
    sid, h = start(c, join_code, pid)
    for seq, i in enumerate(range(0, len(events), LOAD_BATCH), start=1):
        c.post(f"/sessions/{sid}/events", headers=h, json={"seq": seq, "events": events[i:i + LOAD_BATCH]}).raise_for_status()
    t0 = time.perf_counter()
    r = c.post(f"/sessions/{sid}/end", headers=h, json={"respuesta": "Respuesta sintética."})
    dt = time.perf_counter() - t0
    r.raise_for_status()
    assert r.json()["procesada"] is True
    return {"session_id": sid, "end_s": dt, "events": len(events)}


def time_queries(c: httpx.Client, token: str, exam_id: str, session_ids: list[str], reps: int, rng: random.Random) -> dict:
    H = {"Authorization": f"Bearer {token}"}
    out = {"listado": [], "detalle": [], "panorama": []}
    errors = 0
    for _ in range(reps):
        for name, path in (("listado", f"/sessions?exam_id={exam_id}"),
                           ("detalle", f"/sessions/{rng.choice(session_ids)}"),
                           ("panorama", f"/exams/{exam_id}/panorama")):
            t0 = time.perf_counter()
            try:
                r = c.get(path, headers=H)
                ok = r.status_code == 200
            except httpx.HTTPError:
                ok = False
            out[name].append(time.perf_counter() - t0)
            errors += 0 if ok else 1
    return {**out, "errores": errors}


# ---------------------------------------------------------------- RNF11

def rnf11(api: str, token: str, args, rng_np, params) -> dict:
    res: dict = {}
    c = httpx.Client(base_url=api, timeout=120)
    exam = create_exam(c, token, f"RNF11 — {args.sesiones} sesiones sintéticas")
    ends, ids, n_events = [], [], []
    t_load = time.perf_counter()
    for i in range(args.sesiones):
        profile = "normal" if i % 10 else random.Random(i).choice(["pegado_masivo", "cambio_pestana", "tecleo_automatizado", "ritmo_distinto"])
        r = load_and_end(c, exam["join_code"], f"SINT-{i + 1:03d}", synthetic_events(rng_np, params, 1, profile))
        ends.append(r["end_s"])
        ids.append(r["session_id"])
        n_events.append(r["events"])
        if (i + 1) % 100 == 0:
            print(f"  rnf11: {i + 1}/{args.sesiones} sesiones cargadas ({time.perf_counter() - t_load:.0f} s)", flush=True)
    res["cohorte"] = {"exam_id": exam["id"], "sesiones": len(ids), "eventos_por_sesion": stats(n_events),
                      "eventos_total": int(sum(n_events)), "carga_s": time.perf_counter() - t_load}
    res["procesamiento_end_s"] = stats(ends)
    res["_muestras_end_s"] = ends

    # Verificación: con /end ya respondido, el detalle trae métricas e indicadores.
    H = {"Authorization": f"Bearer {token}"}
    d = c.get(f"/sessions/{ids[0]}", headers=H).json()
    res["verificacion_detalle_tras_end"] = bool(d["procesada"] and d["metrics"])

    # Barrido por tamaño de sesión (exam aparte para no alterar la cohorte de 500).
    sweep_exam = create_exam(c, token, "RNF11 — barrido por tamaño de sesión")
    res["barrido"] = []
    for factor in args.barrido:
        reps = 5 if factor <= 10 else 3
        samples, evs = [], []
        for k in range(reps):
            r = load_and_end(c, sweep_exam["join_code"], f"BARRIDO-{factor}-{k}", synthetic_events(rng_np, params, factor))
            samples.append(r["end_s"])
            evs.append(r["events"])
        res["barrido"].append({"factor": factor, "eventos_medio": float(np.mean(evs)), **stats(samples)})
        print(f"  rnf11: barrido x{factor} (~{np.mean(evs):.0f} eventos): p50 {np.median(samples):.2f} s", flush=True)

    # Consultas docentes con la evaluación abierta (todas "pendiente").
    qrng = random.Random(args.semilla)
    q_open = time_queries(c, token, exam["id"], ids, args.repeticiones, qrng)

    # Cierre: análisis poblacional sobre la cohorte completa (una sola vez por evaluación).
    t0 = time.perf_counter()
    r = c.post(f"/exams/{exam['id']}/cerrar", headers=H, timeout=600)
    res["cierre_s"] = time.perf_counter() - t0
    r.raise_for_status()
    pan = c.get(f"/exams/{exam['id']}/panorama", headers=H).json()
    res["cierre_cobertura"] = pan.get("cobertura")

    # Mismo análisis, fuera de línea (función pura), para separar el costo del modelo.
    from app.processing.anomaly import CONTINUOUS_METRICS
    from app.processing.cohort import analizar_cohorte
    metrics = {}
    for sid in ids:
        det = c.get(f"/sessions/{sid}", headers=H).json()
        metrics[sid] = {m["name"]: m["value"] for m in det["metrics"] if m["item_ref"] is None and m["name"] in CONTINUOUS_METRICS}
    offline = []
    for _ in range(3):
        t0 = time.perf_counter()
        out = analizar_cohorte(metrics)
        offline.append(time.perf_counter() - t0)
    res["cohorte_modelo_offline_s"] = stats(offline)
    res["cohorte_marcadas"] = sum(1 for v in out.values() if v is not None and v.is_anomalous)

    q_closed = time_queries(c, token, exam["id"], ids, args.repeticiones, qrng)
    res["consultas_abierta"] = {k: (stats(v) if isinstance(v, list) else v) for k, v in q_open.items()}
    res["consultas_cerrada"] = {k: (stats(v) if isinstance(v, list) else v) for k, v in q_closed.items()}
    res["_ids"] = ids
    c.close()
    return res


# ---------------------------------------------------------------- RNF09

def rnf09(api: str, token: str, args, params, cohort: dict) -> dict:
    exam_id, ids = cohort["exam_id"], cohort["ids"]
    setup = httpx.Client(base_url=api, timeout=120)
    exam = create_exam(setup, token, f"RNF09 — {args.concurrentes} sesiones concurrentes")
    setup.close()

    stop = threading.Event()
    lock = threading.Lock()
    batch_lat, batch_err, err_detail = [], [0], {}
    end_lat, end_err = [], [0]
    barrier = threading.Barrier(args.concurrentes + 1)
    end_go = threading.Event()
    ev_sent = [0]

    def note_err(kind: str):
        with lock:
            err_detail[kind] = err_detail.get(kind, 0) + 1

    def student(i: int):
        rng = np.random.default_rng(10_000 + i)
        events = synthetic_events(rng, params, 3)  # alcanza para la duración de la carga
        c = httpx.Client(base_url=api, timeout=60)
        try:
            sid, h = start(c, exam["join_code"], f"CONC-{i:03d}")
        except Exception as e:  # noqa: BLE001
            note_err(f"start:{type(e).__name__}")
            barrier.wait()
            end_go.wait()
            return
        barrier.wait()
        time.sleep(random.Random(i).uniform(0, BATCH_INTERVAL_S))  # los estudiantes no están sincronizados
        seq, window_start, idx = 0, 0.0, 0
        while not stop.is_set():
            window_end = window_start + BATCH_INTERVAL_S * 1000
            batch = []
            while idx < len(events) and events[idx]["t"] < window_end:
                batch.append(events[idx])
                idx += 1
            window_start = window_end
            if batch:
                seq += 1
                t0 = time.perf_counter()
                ok = False
                for attempt in range(2):  # un reintento ante error de transporte, como syncQueue.ts (idempotente por seq)
                    try:
                        r = c.post(f"/sessions/{sid}/events", headers=h, json={"seq": seq, "events": batch})
                        ok = r.status_code == 201
                        if not ok:
                            note_err(f"events:{r.status_code}")
                        break
                    except httpx.TransportError as e:
                        note_err(f"events:{type(e).__name__}" + (":reintentado" if attempt == 0 else ""))
                    except httpx.HTTPError as e:
                        note_err(f"events:{type(e).__name__}")
                        break
                dt = time.perf_counter() - t0
                with lock:
                    batch_lat.append(dt)
                    if ok:
                        ev_sent[0] += len(batch)
                    else:
                        batch_err[0] += 1
                stop.wait(max(0.0, BATCH_INTERVAL_S - dt))
            else:
                stop.wait(BATCH_INTERVAL_S)
        end_go.wait()
        t0 = time.perf_counter()
        try:
            r = c.post(f"/sessions/{sid}/end", headers=h, json={"respuesta": "r"}, timeout=300)
            ok = r.status_code == 200 and r.json().get("procesada") is True
            if not ok:
                note_err(f"end:{r.status_code}")
        except httpx.HTTPError as e:
            ok = False
            note_err(f"end:{type(e).__name__}")
        with lock:
            end_lat.append(time.perf_counter() - t0)
            if not ok:
                end_err[0] += 1
        c.close()

    threads = [threading.Thread(target=student, args=(i,), daemon=True) for i in range(args.concurrentes)]
    for t in threads:
        t.start()
    barrier.wait()
    print(f"  rnf09: {args.concurrentes} sesiones activas; carga durante {args.duracion_carga} s", flush=True)

    teacher = httpx.Client(base_url=api, timeout=120)
    qrng = random.Random(args.semilla + 1)
    q = {"listado": [], "detalle": [], "panorama": [], "errores": 0}
    t_end = time.time() + args.duracion_carga
    time.sleep(min(BATCH_INTERVAL_S, args.duracion_carga / 4))  # que la carga ya esté en régimen
    while time.time() < t_end:
        part = time_queries(teacher, token, exam_id, ids, 1, qrng)
        for k in ("listado", "detalle", "panorama"):
            q[k] += part[k]
        q["errores"] += part["errores"]
        time.sleep(0.5)
    stop.set()
    time.sleep(0.5)
    print("  rnf09: ráfaga de entregas", flush=True)
    t_burst = time.perf_counter()
    end_go.set()
    for t in threads:
        t.join(timeout=600)
    burst_total = time.perf_counter() - t_burst
    teacher.close()
    return {
        "concurrentes": args.concurrentes, "duracion_s": args.duracion_carga,
        "lotes": stats(batch_lat), "lotes_errores": batch_err[0], "eventos_enviados": ev_sent[0],
        "lotes_por_s": len(batch_lat) / args.duracion_carga,
        "consultas_bajo_carga": {k: (stats(v) if isinstance(v, list) else v) for k, v in q.items()},
        "rafaga_end": stats(end_lat), "rafaga_end_errores": end_err[0], "rafaga_total_s": burst_total,
        "errores_detalle": err_detail,
    }


# ---------------------------------------------------------------- RNF07

INIT_SCRIPT = r"""
(() => {
  const TYPES = new Set(["keydown","keyup","mousemove","mousedown","mouseup","click","scroll",
                         "visibilitychange","blur","focus","paste","copy","cut"]);
  const stats = (window.__capStats = {});
  const orig = EventTarget.prototype.addEventListener;
  const origRm = EventTarget.prototype.removeEventListener;
  const wrapped = new WeakMap();
  EventTarget.prototype.addEventListener = function (type, listener, opts) {
    if ((this === document || this === window) && TYPES.has(type) && typeof listener === "function") {
      const w = function (ev) {
        const t0 = performance.now();
        try { return listener.call(this, ev); }
        finally { (stats[type] ||= []).push(performance.now() - t0); }
      };
      wrapped.set(listener, w);
      return orig.call(this, type, w, opts);
    }
    return orig.call(this, type, listener, opts);
  };
  EventTarget.prototype.removeEventListener = function (type, listener, opts) {
    return origRm.call(this, type, wrapped.get(listener) || listener, opts);
  };
  window.__longtasks = [];
  try { new PerformanceObserver((l) => { for (const e of l.getEntries()) window.__longtasks.push(e.duration); })
          .observe({ type: "longtask", buffered: true }); } catch (e) {}
  window.__eventTiming = [];
  try { new PerformanceObserver((l) => { for (const e of l.getEntries())
          window.__eventTiming.push({ name: e.name, duration: e.duration, processing: e.processingEnd - e.processingStart }); })
          .observe({ type: "event", buffered: true, durationThreshold: 16 }); } catch (e) {}
})();
"""


def build_dashboard_copy(api_url: str, work: Path) -> Path:
    """Copia src/ y la configuración del dashboard a `work` (node_modules por enlace) y compila
    con vite. No ejecuta `tsc -b` para no escribir en el dashboard compartido."""
    dst = work / "dashboard"
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True)
    for name in ("src", "index.html", "package.json", "vite.config.ts", "tsconfig.json", "tsconfig.app.json", "tsconfig.node.json"):
        p = DASHBOARD / name
        if p.is_dir():
            shutil.copytree(p, dst / name)
        elif p.exists():
            shutil.copy2(p, dst / name)
    (dst / "node_modules").symlink_to(DASHBOARD / "node_modules")
    subprocess.run(["npx", "vite", "build", "--outDir", str(dst / "dist"), "--emptyOutDir"], cwd=dst, check=True,
                   env={**os.environ, "VITE_API_URL": api_url}, stdout=subprocess.DEVNULL)
    return dst


def rnf07(api: str, token: str, args, work: Path) -> dict:
    from playwright.sync_api import sync_playwright

    web = f"http://localhost:{args.web_port}"
    dash = build_dashboard_copy(f"http://localhost:{args.api_port}", work)
    preview = subprocess.Popen(["npx", "vite", "preview", "--port", str(args.web_port), "--strictPort", "--outDir", "dist"],
                               cwd=dash, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    results = []
    try:
        wait_http(web)
        c = httpx.Client(base_url=api, timeout=60)
        exam = create_exam(c, token, "RNF07 — costo de la captura")
        c.close()
        text = ("La normalizacion reduce la redundancia y evita anomalias de actualizacion. "
                "Una clave foranea referencia la clave primaria de otra tabla. ") * 2
        with sync_playwright() as p:
            browser = p.chromium.launch()
            for throttle in (1, 4):
                ctx = browser.new_context(viewport={"width": 1280, "height": 800}, locale="es-AR")
                ctx.add_init_script(INIT_SCRIPT)
                page = ctx.new_page()
                cdp = ctx.new_cdp_session(page)
                if throttle > 1:
                    cdp.send("Emulation.setCPUThrottlingRate", {"rate": throttle})
                page.goto(f"{web}/exam/{exam['join_code']}")
                page.wait_for_selector("text=Qué se registra")
                page.fill("input[placeholder^='ej. P-017']", f"RNF07-x{throttle}")
                page.check("input[type=checkbox]")
                page.click("button[type=submit]")
                page.wait_for_selector("text=Consigna")
                page.click("textarea")
                # Solo cuenta lo que ocurre mientras se escribe (no la carga de la página ni el inicio).
                page.evaluate("() => { for (const k in window.__capStats) delete window.__capStats[k]; "
                              "window.__longtasks.length = 0; window.__eventTiming.length = 0; }")
                rng = random.Random(throttle)
                t0 = time.time()
                for k, ch in enumerate(text):
                    key = "Space" if ch == " " else ch
                    page.keyboard.down(key)
                    page.wait_for_timeout(rng.uniform(40, 90))
                    page.keyboard.up(key)
                    page.wait_for_timeout(rng.uniform(30, 90))
                    if k % 15 == 0:  # movimiento de mouse entre palabras
                        x, y = rng.uniform(100, 1100), rng.uniform(100, 700)
                        page.mouse.move(x, y, steps=25)
                page.wait_for_timeout(int(BATCH_INTERVAL_S * 1000) + 1500)  # incluye al menos un envío de lote
                data = page.evaluate("() => ({stats: window.__capStats, longtasks: window.__longtasks, et: window.__eventTiming})")
                elapsed = time.time() - t0
                page.get_by_role("button", name="Finalizar y entregar").click()
                page.wait_for_timeout(1500)
                ctx.close()
                per_type = {k: stats(v) for k, v in data["stats"].items()}
                all_samples = [x for v in data["stats"].values() for x in v]
                et = data["et"]
                results.append({
                    "cpu_throttle": throttle, "duracion_s": elapsed, "caracteres": len(text),
                    "handlers_por_tipo": per_type, "handlers_todos_ms": stats(all_samples),
                    "longtasks_n": len(data["longtasks"]), "longtasks_max_ms": max(data["longtasks"], default=0.0),
                    "event_timing_n_16ms": len(et),
                    "event_timing_max_processing_ms": max((e["processing"] for e in et), default=0.0),
                    "event_timing_max_duration_ms": max((e["duration"] for e in et), default=0.0),
                })
                print(f"  rnf07: CPU x{throttle}: {len(all_samples)} ejecuciones de handlers, "
                      f"máx {max(all_samples, default=0):.2f} ms, tareas largas {len(data['longtasks'])}", flush=True)
            results_browser = browser.version
            browser.close()
    finally:
        import signal
        os.killpg(preview.pid, signal.SIGTERM)  # npx + vite (el hijo no muere con terminate())
    return {"chromium": results_browser, "corridas": results}


# ---------------------------------------------------------------- informe

def fmt_s(st: dict, unit: str = "s") -> str:
    if not st or not st.get("n"):
        return "—"
    if unit == "ms_from_s":
        return f"{st['p50'] * 1000:.0f} / {st['p95'] * 1000:.0f} / {st['max'] * 1000:.0f} ms"
    if unit == "ms":
        return f"{st['p50']:.3f} / {st['p95']:.3f} / {st['max']:.3f} ms"
    return f"{st['p50']:.2f} / {st['p95']:.2f} / {st['max']:.2f} s"


def verdict(value: float, bound: float) -> str:
    return "cumple" if value <= bound else "**no cumple**"


def write_report(paths: list[Path], out: Path) -> None:
    runs = [json.loads(p.read_text()) for p in paths]
    L = ["# Mediciones de requisitos no funcionales de rendimiento (RNF07, RNF09, RNF11)", "",
         f"_Generado por `scripts/medir_rnf.py --informe` el {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC a partir de "
         + ", ".join(f"`{p.name}`" for p in paths) + ". No editar a mano: regenerar con el script._", "",
         "> Mediciones sobre el sistema real (backend FastAPI con uvicorn en un proceso, como el Dockerfile; "
         "dashboard compilado en Chromium) con sesiones **sintéticas** (`app/evaluation/synthetic.py`). "
         "Los tiempos de servidor se miden del lado del cliente HTTP, en la misma máquina que el servidor. "
         "Valores p50 / p95 / máximo.", "", "## Entorno", "",
         "| Corrida | CPU | RAM | SO | Python | Base |", "|---|---|---|---|---|---|"]
    for r in runs:
        e = r["entorno"]
        L.append(f"| {r['etiqueta']} | {e['cpus']} × {e['cpu_model']} | {e['ram_gb']} GB | {e['os']} | {e['python']} | "
                 f"{e['motor']} {e['motor_version']} |")
    L += ["", "## Resultados", "",
          "| Requisito | Cota | Medición | Corrida | p50 / p95 / máx | Resultado |", "|---|---|---|---|---|---|"]
    for r in runs:
        tag = r["etiqueta"]
        if "rnf11" in r:
            x = r["rnf11"]
            co = x["cohorte"]
            L.append(f"| RNF11 procesamiento por sesión | 5 s | `/end` → indicadores disponibles, {co['sesiones']} sesiones "
                     f"(~{co['eventos_por_sesion']['mean']:.0f} eventos c/u) | {tag} | {fmt_s(x['procesamiento_end_s'], 'ms_from_s')} | "
                     f"{verdict(x['procesamiento_end_s']['max'], 5.0)} |")
            for b in x["barrido"]:
                L.append(f"| RNF11 procesamiento por sesión | 5 s | sesión de ~{b['eventos_medio']:.0f} eventos (n={b['n']}) | {tag} | "
                         f"{fmt_s(b, 'ms_from_s')} | {verdict(b['max'], 5.0)} |")
            for estado, key in (("abierta", "consultas_abierta"), ("cerrada", "consultas_cerrada")):
                for qn, label in (("listado", "listado de sesiones"), ("detalle", "detalle de sesión"), ("panorama", "panorama")):
                    st = x[key][qn]
                    L.append(f"| RNF11 consultas docentes | 2 s | {label}, {co['sesiones']} sesiones, evaluación {estado} | {tag} | "
                             f"{fmt_s(st, 'ms_from_s')} | {verdict(st['max'], 2.0)} |")
            L.append(f"| (Inc. 16) cierre de la evaluación | sin cota | `POST /exams/{{id}}/cerrar`, {co['sesiones']} sesiones (1 medición) | {tag} | "
                     f"{x['cierre_s']:.2f} s | — |")
            L.append(f"| (Inc. 16) modelo sobre la cohorte | sin cota | `analizar_cohorte` fuera de línea (n=3) | {tag} | "
                     f"{fmt_s(x['cohorte_modelo_offline_s'])} | — |")
        if "rnf09" in r:
            y = r["rnf09"]
            n = y["concurrentes"]
            L.append(f"| RNF09 concurrencia | {n} sesiones activas | lotes cada 5 s durante {y['duracion_s']} s "
                     f"({y['lotes']['n']} lotes, {y['lotes_errores']} errores) | {tag} | {fmt_s(y['lotes'], 'ms_from_s')} | "
                     f"{'cumple' if y['lotes_errores'] == 0 else '**no cumple**'} |")
            for qn, label in (("listado", "listado"), ("detalle", "detalle"), ("panorama", "panorama")):
                st = y["consultas_bajo_carga"][qn]
                L.append(f"| RNF09 + RNF11 consultas bajo carga | 2 s | {label} ({r['rnf11']['cohorte']['sesiones']} sesiones) con {n} activas | {tag} | "
                         f"{fmt_s(st, 'ms_from_s')} | {verdict(st['max'], 2.0)} |")
            L.append(f"| RNF09 + RNF11 entrega simultánea | 5 s | {n} `/end` a la vez ({y['rafaga_end_errores']} errores) | {tag} | "
                     f"{fmt_s(y['rafaga_end'], 'ms_from_s')} | {verdict(y['rafaga_end']['max'], 5.0) if y['rafaga_end_errores'] == 0 else '**no cumple**'} |")
        if "rnf07" in r:
            for run in r["rnf07"]["corridas"]:
                st = run["handlers_todos_ms"]
                L.append(f"| RNF07 costo por evento en el navegador | 50 ms | handlers de captura, CPU ×{run['cpu_throttle']} "
                         f"({st['n']} ejecuciones; {run['longtasks_n']} tareas largas) | {tag} | {fmt_s(st, 'ms')} | "
                         f"{verdict(st['max'], 50.0)} |")
    L += ["", "## Detalle", ""]
    for r in runs:
        tag = r["etiqueta"]
        L.append(f"### Corrida `{tag}` ({r['fecha']})")
        L.append("")
        L.append(f"Parámetros: `{json.dumps(r['parametros'], ensure_ascii=False)}`.")
        if r.get("carga_sistema"):
            L.append(f"Carga del sistema (loadavg 1/5/15 min) antes y después de cada fase: `{r['carga_sistema']}` "
                     "(otros procesos de la máquina compartida también la afectan).")
        L.append("")
        if "rnf11" in r:
            x = r["rnf11"]
            co = x["cohorte"]
            L.append(f"- Cohorte: {co['sesiones']} sesiones, {co['eventos_total']} eventos en total "
                     f"(por sesión p50 {co['eventos_por_sesion']['p50']:.0f}, máx {co['eventos_por_sesion']['max']:.0f}); "
                     f"carga por la API en {co['carga_s']:.0f} s. Detalle verificado tras `/end`: {x['verificacion_detalle_tras_end']}.")
            cob = x.get("cierre_cobertura") or {}
            L.append(f"- Cierre: {x['cierre_s']:.2f} s; cobertura tras el cierre: {cob}. Sesiones marcadas por el modelo "
                     f"(fuera de línea): {x['cohorte_marcadas']}.")
            for estado, key in (("abierta", "consultas_abierta"), ("cerrada", "consultas_cerrada")):
                L.append(f"- Consultas con la evaluación {estado}: errores {x[key]['errores']}; media listado "
                         f"{x[key]['listado']['mean'] * 1000:.0f} ms, detalle {x[key]['detalle']['mean'] * 1000:.0f} ms, "
                         f"panorama {x[key]['panorama']['mean'] * 1000:.0f} ms.")
        if "rnf09" in r:
            y = r["rnf09"]
            L.append(f"- Concurrencia: {y['lotes']['n']} lotes ({y['lotes_por_s']:.1f}/s), {y['eventos_enviados']} eventos guardados, "
                     f"errores de lotes {y['lotes_errores']}, errores de consultas {y['consultas_bajo_carga']['errores']}, "
                     f"ráfaga de {y['concurrentes']} entregas completada en {y['rafaga_total_s']:.1f} s "
                     f"(errores {y['rafaga_end_errores']}). Errores por tipo: {y['errores_detalle'] or 'ninguno'}.")
        if "rnf07" in r:
            L.append(f"- Navegador: Chromium {r['rnf07']['chromium']} (headless).")
            for run in r["rnf07"]["corridas"]:
                tipos = ", ".join(f"{k} n={v['n']} máx {v['max']:.2f} ms" for k, v in sorted(run["handlers_por_tipo"].items()))
                L.append(f"  - CPU ×{run['cpu_throttle']}: {run['caracteres']} caracteres en {run['duracion_s']:.0f} s; {tipos}. "
                         f"Tareas largas: {run['longtasks_n']} (máx {run['longtasks_max_ms']:.0f} ms). Event Timing (página completa, "
                         f"entradas ≥ 16 ms): {run['event_timing_n_16ms']}, procesamiento máx {run['event_timing_max_processing_ms']:.1f} ms, "
                         f"duración máx {run['event_timing_max_duration_ms']:.1f} ms.")
        L.append("")
    L += ["## Limitaciones", "",
          "- **Datos sintéticos.** Volumen y forma de los eventos vienen del generador de la evaluación (≈ 2 minutos de "
          "escritura por sesión); un examen real dura más. El barrido por tamaño de sesión cubre sesiones más largas.",
          "- **Una sola máquina.** Cliente de carga (hilos de Python), servidor y base comparten las mismas CPU: los "
          "tiempos incluyen la contención del propio generador de carga (pesimista para el servidor) y no incluyen la "
          "latencia de una red real ni la de un servicio gestionado (Render, Neon).",
          "- **Un proceso de uvicorn**, como el Dockerfile; con más procesos o más CPU los números cambian.",
          "- **Reintentos.** Como `syncQueue.ts`, el generador reintenta una vez un lote que falla por un error de "
          "transporte (conexión cerrada por el servidor al vencer su keep-alive de 5 s, igual al intervalo de envío); "
          "esos casos figuran como `…:reintentado` en los errores por tipo y solo cuentan como error si el reintento "
          "también falla. `/end` no se reintenta (en el dashboard el reintento es manual).",
          "- **El cierre se mide una vez por corrida** (es una operación única por evaluación); el costo del modelo se "
          "repite fuera de línea.",
          "- **RNF07** mide los handlers de captura registrados en `document`/`window` (capture.ts + keyPairing.ts, "
          "incluido el encolado del evento), no el renderizado de React del área de texto, que se informa aparte "
          "(Event Timing). Chromium headless; `performance.now()` tiene resolución reducida (≈ 0,1 ms) sin aislamiento "
          "de origen, por lo que los valores por debajo de esa resolución aparecen como 0 o 0,1 ms.",
          ""]
    out.write_text("\n".join(L), encoding="utf-8")
    print(f"Informe: {out}")


# ---------------------------------------------------------------- main

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--etiqueta", default="sqlite", help="nombre de la corrida (archivo rnf_mediciones_<etiqueta>.json)")
    ap.add_argument("--db-url", default=None, help="DATABASE_URL; por defecto SQLite en un directorio temporal")
    ap.add_argument("--pruebas", default="rnf11,rnf09,rnf07")
    ap.add_argument("--sesiones", type=int, default=500)
    ap.add_argument("--barrido", default="1,10,50", help="tamaños de sesión, en múltiplos de una sesión sintética")
    ap.add_argument("--repeticiones", type=int, default=30, help="repeticiones de cada consulta docente")
    ap.add_argument("--concurrentes", type=int, default=200)
    ap.add_argument("--duracion-carga", type=int, default=60)
    ap.add_argument("--semilla", type=int, default=2026)
    ap.add_argument("--api-port", type=int, default=8131)
    ap.add_argument("--web-port", type=int, default=5191)
    ap.add_argument("--backend-python", default=sys.executable)
    ap.add_argument("--salida", type=Path, default=OUT_DIR)
    ap.add_argument("--informe", nargs="+", type=Path, help="genera rnf_mediciones.md a partir de estos JSON y termina")
    args = ap.parse_args(argv)

    if args.informe:
        write_report(args.informe, args.salida / "rnf_mediciones.md")
        return 0

    args.barrido = [int(x) for x in args.barrido.split(",") if x]
    pruebas = set(args.pruebas.split(","))
    work = Path(tempfile.mkdtemp(prefix="rnf_"))
    db_url = args.db_url or f"sqlite:///{work / 'rnf.db'}"
    if not db_url.startswith("sqlite"):
        reset_postgres(db_url)

    result = {"etiqueta": args.etiqueta, "fecha": f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC",
              "parametros": {k: (str(v) if isinstance(v, Path) else v) for k, v in vars(args).items() if k not in ("informe",)},
              "entorno": environment(db_url)}
    print(f"Entorno: {result['entorno']}", flush=True)
    backend = Backend(args.backend_python, db_url, args.api_port, f"http://localhost:{args.web_port}")
    try:
        token = login(backend.url)
        params = SyntheticParams()
        rng_np = np.random.default_rng(args.semilla)
        if "rnf11" in pruebas or "rnf09" in pruebas:
            print("RNF11…", flush=True)
            result["carga_sistema"] = {"antes": os.getloadavg()}
            r11 = rnf11(backend.url, token, args, rng_np, params)
            result["carga_sistema"]["tras_rnf11"] = os.getloadavg()
            ids = r11.pop("_ids")
            result["rnf11"] = r11
            if "rnf09" in pruebas:
                print("RNF09…", flush=True)
                result["rnf09"] = rnf09(backend.url, token, args, params, {"exam_id": r11["cohorte"]["exam_id"], "ids": ids})
                result["carga_sistema"]["tras_rnf09"] = os.getloadavg()
        if "rnf07" in pruebas:
            print("RNF07…", flush=True)
            result["rnf07"] = rnf07(backend.url, token, args, work)
    finally:
        backend.stop()
    out = args.salida / f"rnf_mediciones_{args.etiqueta}.json"
    out.write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"Resultados: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
