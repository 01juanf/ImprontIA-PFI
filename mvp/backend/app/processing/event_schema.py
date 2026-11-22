"""
Validación de eventos en el servidor (Incremento 16).

La captura del navegador ya filtra por la política de la sesión (capture.ts), pero las
garantías de minimización (RNF01, RF04) no pueden depender solo del cliente: el backend
rechaza cualquier lote que traiga un tipo de evento desconocido, una categoría que la
política de la sesión no habilita, un campo que no corresponde al tipo (por ejemplo,
`key` o `code`, que identificarían la tecla) o un valor fuera de su formato.

Función pura: no accede a la base. Devuelve la lista de problemas (vacía = lote válido).
"""
import math
from numbers import Real
from typing import Any, Callable, Optional

MAX_EVENTS_PER_BATCH = 5000
MAX_ITEM_REF_LEN = 64


def _num(v: Any) -> bool:
    # Finito: el JSON de entrada admite NaN/Infinity, que luego rompían métricas y respuestas.
    return isinstance(v, Real) and not isinstance(v, bool) and math.isfinite(v)


def _nonneg_num(v: Any) -> bool:
    return _num(v) and v >= 0


def _nonneg_int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and v >= 0


def _opt(check: Callable[[Any], bool]) -> Callable[[Any], bool]:
    return lambda v: v is None or check(v)


# tipo -> (categoría de señal que lo habilita, {campo: validador}).
# Categoría None = evento de estado de la propia captura (siempre admitido).
EVENT_SCHEMAS: dict[str, tuple[Optional[str], dict[str, Callable[[Any], bool]]]] = {
    "keydown": ("keyboard", {}),
    # dwell: duración de la pulsación calculada en el navegador sin enviar la tecla
    # (None = liberación sin pulsación registrada, p. ej. tras volver el foco).
    "keyup": ("keyboard", {"dwell": _opt(_nonneg_num)}),
    "mousemove": ("mouse", {"x": _num, "y": _num}),
    "mousedown": ("mouse", {"button": _nonneg_int, "x": _num, "y": _num}),
    "mouseup": ("mouse", {"button": _nonneg_int, "x": _num, "y": _num}),
    "click": ("mouse", {"x": _num, "y": _num}),
    "scroll": ("scroll", {"scrollX": _num, "scrollY": _num}),
    "visibility": ("visibility", {"state": lambda v: v in ("hidden", "visible")}),
    "window_blur": ("visibility", {}),
    "window_focus": ("visibility", {}),
    "paste": ("clipboard", {"chars": _nonneg_int}),
    "copy": ("clipboard", {}),
    "cut": ("clipboard", {}),
    "buffer_overflow": (None, {"dropped": _nonneg_int, "from_t": _opt(_num), "to_t": _opt(_num)}),
    "sync_failure": (None, {"failed_attempts": _nonneg_int, "duration_ms": _nonneg_num}),
}

COMMON_FIELDS = {"t", "type", "item_ref"}


def validate_batch(events: list[dict], allowed_signals: list[str]) -> list[str]:
    """Problemas encontrados en el lote, con el índice del evento (vacía = válido)."""
    problems: list[str] = []
    if len(events) > MAX_EVENTS_PER_BATCH:
        return [f"el lote supera {MAX_EVENTS_PER_BATCH} eventos"]
    allowed = set(allowed_signals or [])
    for i, e in enumerate(events):
        if not isinstance(e, dict):
            problems.append(f"evento {i}: no es un objeto")
            continue
        etype = e.get("type")
        if etype not in EVENT_SCHEMAS:
            problems.append(f"evento {i}: tipo desconocido {etype!r}")
            continue
        category, fields = EVENT_SCHEMAS[etype]
        if category is not None and category not in allowed:
            problems.append(f"evento {i}: la categoría {category!r} no está habilitada en la política de la sesión")
        if not _nonneg_num(e.get("t")):
            problems.append(f"evento {i}: 't' debe ser un número no negativo")
        ref = e.get("item_ref")
        if ref is not None and not (isinstance(ref, str) and 0 < len(ref) <= MAX_ITEM_REF_LEN):
            problems.append(f"evento {i}: 'item_ref' inválido")
        extra = set(e) - COMMON_FIELDS - set(fields)
        if extra:
            problems.append(f"evento {i}: campos no admitidos para {etype!r}: {sorted(extra)}")
        for name, check in fields.items():
            if name in e and not check(e[name]):
                problems.append(f"evento {i}: valor inválido en {name!r}")
    return problems
