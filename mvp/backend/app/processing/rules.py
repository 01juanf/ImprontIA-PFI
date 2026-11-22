"""
Reglas del examen que cambian la RELEVANCIA de algunos eventos (Incremento 12, R2).

Si el docente permite pegar texto o consultar otras pestañas, que eso ocurra no es
algo que haya que mirar: el indicador se sigue generando (trazabilidad), pero con
nivel bajo, la aclaración "permitido por las reglas de esta evaluación" y sin
priorizar la sesión para revisión.

Sin cambio de esquema: las reglas se guardan como entradas reservadas dentro del
JSON `PolicyCapture.allowed_signals` (p. ej. "regla:permite_pegado") y la API las
expone como booleanos separados. Las entradas reservadas nunca llegan al cliente de
captura ni a la lista de señales que ve el estudiante. Sin reglas (el valor por
defecto, y el de todas las políticas anteriores al Incremento 12) el comportamiento
es exactamente el de antes.
"""

RULE_PREFIX = "regla:"
RULE_FLAGS = ("permite_pegado", "permite_otras_pestanas")

# Qué indicador se vuelve "permitido" con cada regla.
RULE_KINDS = {
    "permite_pegado": ("paste_volume_alto",),
    "permite_otras_pestanas": ("cambios_pestana_frecuentes", "perdida_foco_prolongada"),
}

PERMITTED_NOTE = "permitido por las reglas de esta evaluación"


def capture_signals(stored: list[str] | None) -> list[str]:
    """Señales de captura reales (sin las entradas reservadas de reglas)."""
    return [s for s in (stored or []) if not str(s).startswith(RULE_PREFIX)]


def rules_from_stored(stored: list[str] | None) -> dict[str, bool]:
    present = {str(s)[len(RULE_PREFIX):] for s in (stored or []) if str(s).startswith(RULE_PREFIX)}
    return {flag: flag in present for flag in RULE_FLAGS}


def to_stored(signals: list[str], rules: dict[str, bool] | None = None) -> list[str]:
    """Lista a guardar en `allowed_signals`: señales + una entrada por regla activa."""
    rules = rules or {}
    return capture_signals(signals) + [RULE_PREFIX + f for f in RULE_FLAGS if rules.get(f)]


def permitted_kinds(rules: dict[str, bool] | None) -> set[str]:
    kinds: set[str] = set()
    for flag, active in (rules or {}).items():
        if active:
            kinds.update(RULE_KINDS.get(flag, ()))
    return kinds
