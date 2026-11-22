"""
Extracción determinística de métricas a partir de eventos crudos.

Sin ML: son estadísticas simples (promedios, conteos, duraciones) tal como
lo fija la tesis para el alcance del MVP (cap. 15, "Procesamiento e IA").
Funciones puras -> fáciles de testear unitariamente (requisito de calidad
del cap. 15, sección "Calidad, pruebas y despliegue").

Formato esperado de cada evento (coincide con el exportado por la extensión,
ver extension-mvp/README.md): {"t": <ms relativos al inicio>, "type": <str>, ...campos}
"""
from collections import deque
from statistics import mean, pstdev
from typing import Optional


def _events_of_type(events: list[dict], *types: str) -> list[dict]:
    return [e for e in events if e.get("type") in types]


def compute_keystroke_features(events: list[dict]) -> dict[str, float]:
    """
    Dwell time (keydown->keyup) y flight time (keyup->siguiente keydown).

    Emparejamiento de cada liberación con su pulsación (Incremento 16):

    - **En el navegador** (captura real desde el Incremento 16): `capture.ts` empareja cada
      liberación con la pulsación de la MISMA tecla usando su código solo en memoria, ignora
      la repetición automática y descarta las pulsaciones abiertas al perder el foco. Envía
      `keyup` con `dwell` (ms) y nunca la identidad de la tecla. Si una sesión trae `dwell`,
      se usa tal cual; una liberación con `dwell = None` (sin pulsación registrada) no aporta
      duración.
    - **Por código de tecla** (`code`, solo datos de prueba antiguos).
    - **En orden de llegada** (una cola FIFO): eventos sin `dwell` ni `code`, como los del
      generador sintético, que nunca solapa teclas. Con teclas solapadas y liberadas en otro
      orden este modo intercambia duraciones; por eso la captura real ya no depende de él.
    """
    ordered = sorted(events, key=lambda e: e["t"])
    client_paired = any(e["type"] == "keyup" and "dwell" in e for e in ordered)

    pending: dict[str, deque] = {}
    dwell_times: list[float] = []
    last_keyup_t: Optional[float] = None
    flight_times: list[float] = []

    for e in ordered:
        if e["type"] == "keydown":
            if not client_paired:
                pending.setdefault(e.get("code"), deque()).append(e["t"])
            if last_keyup_t is not None:
                flight_times.append(e["t"] - last_keyup_t)
        elif e["type"] == "keyup":
            if client_paired:
                if e.get("dwell") is not None:
                    dwell_times.append(float(e["dwell"]))
            else:
                q = pending.get(e.get("code"))
                if q:
                    dwell_times.append(e["t"] - q.popleft())
            last_keyup_t = e["t"]

    keydown_count = len(_events_of_type(events, "keydown"))

    return {
        "keydown_count": float(keydown_count),
        "mean_dwell_time_ms": mean(dwell_times) if dwell_times else 0.0,
        "std_dwell_time_ms": pstdev(dwell_times) if len(dwell_times) > 1 else 0.0,
        "mean_flight_time_ms": mean(flight_times) if flight_times else 0.0,
    }


def compute_mouse_features(events: list[dict]) -> dict[str, float]:
    moves = sorted(_events_of_type(events, "mousemove"), key=lambda e: e["t"])
    speeds = []
    for prev, cur in zip(moves, moves[1:]):
        dt = cur["t"] - prev["t"]
        if dt <= 0:
            continue
        dist = ((cur["x"] - prev["x"]) ** 2 + (cur["y"] - prev["y"]) ** 2) ** 0.5
        speeds.append(dist / dt)

    clicks = _events_of_type(events, "click")

    return {
        "mean_mouse_speed_px_ms": mean(speeds) if speeds else 0.0,
        "std_mouse_speed_px_ms": pstdev(speeds) if len(speeds) > 1 else 0.0,
        "click_count": float(len(clicks)),
    }


def compute_attention_features(events: list[dict]) -> dict[str, float]:
    """Cambios de pestaña/foco a partir de eventos de visibilidad."""
    visibility = sorted(_events_of_type(events, "visibility"), key=lambda e: e["t"])

    tab_switch_count = sum(1 for e in visibility if e.get("state") == "hidden")

    focus_loss_total = 0.0
    hidden_since: Optional[float] = None
    for e in visibility:
        if e.get("state") == "hidden":
            hidden_since = e["t"]
        elif e.get("state") == "visible" and hidden_since is not None:
            focus_loss_total += e["t"] - hidden_since
            hidden_since = None

    return {
        "tab_switch_count": float(tab_switch_count),
        "focus_loss_duration_total_ms": focus_loss_total,
    }


def compute_clipboard_features(events: list[dict]) -> dict[str, float]:
    pastes = _events_of_type(events, "paste")
    return {
        "paste_event_count": float(len(pastes)),
        "paste_chars_total": float(sum(e.get("chars", 0) for e in pastes)),
        "copy_cut_count": float(len(_events_of_type(events, "copy", "cut"))),
    }


# Eventos que genera el propio cliente sobre el estado de la captura (Incremento 10), no
# interacciones del estudiante: no cuentan para la duración ni para la inactividad.
CAPTURE_STATUS_TYPES = ("buffer_overflow", "sync_failure")


def compute_capture_integrity(events: list[dict]) -> dict[str, float]:
    """
    Integridad de la captura (cap. 15, "Captura de señales"): eventos descartados por
    agotamiento del buffer local y fallas persistentes de sincronización, que el
    cliente registra como eventos propios en lugar de perder evidencia en silencio.
    """
    overflows = _events_of_type(events, "buffer_overflow")
    return {
        "capture_dropped_events": float(sum(e.get("dropped", 0) for e in overflows)),
        "sync_failure_count": float(len(_events_of_type(events, "sync_failure"))),
    }


def compute_idle_ratio(events: list[dict], gap_threshold_ms: float = 2000.0) -> dict[str, float]:
    """Fracción del tiempo de sesión sin ningún evento (gaps > gap_threshold_ms)."""
    events = [e for e in events if e.get("type") not in CAPTURE_STATUS_TYPES]
    ordered = sorted(events, key=lambda e: e["t"])
    if len(ordered) < 2:
        return {"idle_ratio": 0.0, "session_duration_ms": 0.0}

    duration = ordered[-1]["t"] - ordered[0]["t"]
    if duration <= 0:
        return {"idle_ratio": 0.0, "session_duration_ms": 0.0}

    idle_time = sum(
        gap for gap in (b["t"] - a["t"] for a, b in zip(ordered, ordered[1:]))
        if gap > gap_threshold_ms
    )
    return {"idle_ratio": idle_time / duration, "session_duration_ms": duration}


def compute_all_features(events: list[dict]) -> dict[str, float]:
    features: dict[str, float] = {}
    features.update(compute_keystroke_features(events))
    features.update(compute_mouse_features(events))
    features.update(compute_attention_features(events))
    features.update(compute_clipboard_features(events))
    features.update(compute_idle_ratio(events))
    features.update(compute_capture_integrity(events))
    return features
