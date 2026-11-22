"""
Verificación de humo de un despliegue de ImprontIA (Fase 2, P01).

Recorre por HTTP el flujo completo contra una API ya desplegada (local, Docker Compose,
Render o Railway): salud, login del docente, creación de una evaluación, una sesión de
estudiante con eventos, cierre, detalle, panorama y CORS. No usa nada del código del
backend: solo la API pública, como lo haría el dashboard.

Uso (desde mvp/):

    python scripts/verificar_despliegue.py --api https://improntia-api.onrender.com \
        --email martina@uade.edu.ar --clave '...' --origen https://improntia-dashboard.onrender.com

Deja en la base una evaluación llamada "Verificación de despliegue <fecha>" con una
sesión de prueba (participante VERIF-…), fácil de distinguir de las simulaciones.
Sale con código 0 si todos los chequeos pasan.
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone


def call(api, method, path, body=None, headers=None, timeout=60):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(api.rstrip("/") + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else None), dict(r.headers)
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            payload = json.loads(raw)
        except ValueError:
            payload = raw.decode(errors="replace")
        return e.code, payload, dict(e.headers)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--api", required=True, help="URL base de la API (sin barra final)")
    ap.add_argument("--email", required=True)
    ap.add_argument("--clave", required=True)
    ap.add_argument("--origen", help="URL del dashboard, para verificar CORS")
    args = ap.parse_args(argv)

    resultados = []

    def check(nombre, ok, detalle=""):
        ok = bool(ok)
        resultados.append(ok)
        print(f"[{'OK ' if ok else 'FALLA'}] {nombre}{(' — ' + detalle) if detalle else ''}", flush=True)
        return ok

    # 1. Salud (un servicio gratuito dormido puede tardar ~1 min en despertar).
    t0 = time.time()
    st, body, _ = call(args.api, "GET", "/health", timeout=120)
    check("API responde /health", st == 200 and isinstance(body, dict) and body.get("status") == "ok", f"{time.time() - t0:.1f} s")

    # 2. Login.
    st, body, _ = call(args.api, "POST", "/auth/login", {"email": args.email, "password": args.clave})
    if not check("login del docente", st == 200 and "access_token" in (body or {}), f"HTTP {st}"):
        return 1
    auth = {"Authorization": f"Bearer {body['access_token']}"}
    st, _, _ = call(args.api, "POST", "/auth/login", {"email": args.email, "password": args.clave + "-mal"})
    check("login con clave incorrecta rechazado", st == 401, f"HTTP {st}")
    st, _, _ = call(args.api, "GET", "/exams", headers={"Authorization": "Bearer token-falso"})
    check("token falso rechazado", st == 401, f"HTTP {st}")

    # 3. Evaluación.
    nombre = f"Verificación de despliegue {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC"
    st, exam, _ = call(args.api, "POST", "/exams", {
        "name": nombre, "prompt_text": "Consigna de verificación.", "info_text": "Se registran teclado y portapapeles.",
        "rules_text": "Prueba técnica.", "allowed_signals": ["keyboard", "clipboard", "visibility"],
    }, auth)
    if not check("crear evaluación", st == 200 and exam.get("join_code"), f"código {exam.get('join_code') if st == 200 else st}"):
        return 1

    st, info, _ = call(args.api, "GET", f"/exams/{exam['join_code']}/info")
    check("info pública antes del consentimiento", st == 200 and "prompt_text" not in info)

    # 4. Sesión del estudiante.
    st, s, _ = call(args.api, "POST", "/sessions/start", {
        "exam_code": exam["join_code"], "participant_id": f"VERIF-{int(time.time())}", "consent_given": True, "context": {},
    })
    if not check("iniciar sesión de estudiante", st == 200, f"HTTP {st}"):
        return 1
    h = {"X-Session-Token": s["session_token"]}
    eventos = []
    t = 0.0
    for _ in range(40):
        eventos += [{"t": t, "type": "keydown"}, {"t": t + 90, "type": "keyup"}]
        t += 250
    eventos.append({"t": t, "type": "paste", "chars": 600})
    st, body, _ = call(args.api, "POST", f"/sessions/{s['session_id']}/events", {"seq": 1, "events": eventos}, h)
    check("enviar lote de eventos", st == 201 and body["stored"] == len(eventos), f"{body.get('stored') if st == 201 else st} eventos")
    st, body, _ = call(args.api, "POST", f"/sessions/{s['session_id']}/events", {"seq": 1, "events": eventos}, h)
    check("reintento del mismo lote es idempotente", st == 201 and body["stored"] == 0)
    st, end, _ = call(args.api, "POST", f"/sessions/{s['session_id']}/end", headers=h)
    check("finalizar sesión (pipeline)", st == 200 and end["needs_review"] is True, f"needs_review={end.get('needs_review')}")

    # 5. Vista del docente.
    st, d, _ = call(args.api, "GET", f"/sessions/{s['session_id']}", headers=auth)
    kinds = [i["kind"] for i in d.get("indicators", [])] if st == 200 else []
    check("detalle con métricas e indicador", st == 200 and d["event_count"] == len(eventos) and "paste_volume_alto" in kinds,
          f"{d.get('event_count')} eventos, indicadores {kinds}")
    st, p, _ = call(args.api, "GET", f"/exams/{exam['id']}/panorama", headers=auth)
    check("panorama de la evaluación", st == 200 and p["n_sesiones"] == 1)

    # 6. CORS.
    if args.origen:
        req = urllib.request.Request(args.api.rstrip("/") + "/exams", method="OPTIONS")
        req.add_header("Origin", args.origen)
        req.add_header("Access-Control-Request-Method", "GET")
        req.add_header("Access-Control-Request-Headers", "authorization")
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                allow = r.headers.get("access-control-allow-origin")
                st = r.status
        except urllib.error.HTTPError as e:
            allow, st = e.headers.get("access-control-allow-origin"), e.code
        check("CORS permite el dashboard", st == 200 and allow == args.origen.rstrip("/"), f"allow-origin={allow}")
        req = urllib.request.Request(args.api.rstrip("/") + "/exams", method="OPTIONS")
        req.add_header("Origin", "https://sitio-ajeno.example")
        req.add_header("Access-Control-Request-Method", "GET")
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                allow = r.headers.get("access-control-allow-origin")
        except urllib.error.HTTPError as e:
            allow = e.headers.get("access-control-allow-origin")
        check("CORS rechaza otros orígenes", allow is None, f"allow-origin={allow}")

    ok = all(resultados)
    print(f"\n{sum(resultados)}/{len(resultados)} chequeos OK — {'DESPLIEGUE VERIFICADO' if ok else 'HAY FALLAS'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
