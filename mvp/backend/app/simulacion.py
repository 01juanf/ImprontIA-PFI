"""
Kit de simulación (Fase 2, P03).

Martina y Juan rinden sesiones de prueba declarando una condición simulada
(docs/simulaciones/protocolo.md). La condición se guarda en
`sessions.condicion_simulacion`, nunca se devuelve en la API del docente y el
pipeline no la lee. Solo la usan `scripts/exportar_sesiones.py` y
`scripts/analizar_reales.py`.
"""
CONDICIONES = ("normal", "pegado", "transcripcion", "consulta_externa", "suplantacion")
CONDICION_NORMAL = "normal"
