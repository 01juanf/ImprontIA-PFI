"""
Generador de sesiones SINTÉTICAS (normales y anómalas) para validar el
procedimiento de evaluación del pipeline (Incremento 6, ver mvp/docs/bitacora.md).

Qué es y qué no es
------------------
- Genera eventos crudos con el MISMO formato que produce `capture.ts` en el
  navegador ({"t": ms relativos, "type": ..., campos}), de modo que la
  evaluación ejercita el pipeline completo: eventos -> features.py ->
  indicators.py + anomaly.py.
- Los parámetros de abajo NO están calibrados con datos humanos reales ni
  pretenden representar a ninguna población: son valores elegidos para que
  las sesiones "normales" tengan variación entre participantes y dentro de
  cada sesión, y para que cada perfil anómalo difiera de lo normal de una
  forma controlada. Sirven para validar que el procedimiento de medición
  (FAR/FRR/AUC/EER) funciona de punta a punta, no para estimar el desempeño
  real del sistema — eso depende del piloto (cap. 18).
- Siguiendo la recomendación metodológica de Emmott et al. (2013) para
  benchmarks de anomalías, todos los parámetros que controlan la frecuencia
  relativa de anomalías y la dificultad de detectarlas quedan explícitos y
  se reportan junto con los resultados (ver scripts/evaluar.py).

Perfiles anómalos
-----------------
- `pegado_masivo`: la respuesta se arma pegando un bloque grande de texto
  (señal discreta, la cubre la regla `paste_volume_alto`).
- `cambio_pestana`: salidas frecuentes y/o prolongadas de la pestaña del
  examen (reglas `cambios_pestana_frecuentes` / `perdida_foco_prolongada`).
- `tecleo_automatizado`: pulsaciones con duración casi constante, típico de
  texto inyectado por un script (regla `ritmo_tecleo_atipico`).
- `ritmo_distinto`: dinámica de teclado y mouse desplazada `dificultad`
  desvíos poblacionales respecto de lo normal, sin ninguna señal discreta
  (sólo la puede detectar el modelo poblacional, Isolation Forest).

Los tres primeros perfiles se construyen alrededor de los umbrales de
indicators.py, por lo que su tasa de detección es en buena medida una
verificación de que las reglas se disparan cuando corresponde; el perfil
informativo para el componente de IA es `ritmo_distinto`.
"""
from dataclasses import asdict, dataclass

import numpy as np

PROFILES_ANOMALOS = ["pegado_masivo", "cambio_pestana", "tecleo_automatizado", "ritmo_distinto"]


@dataclass(frozen=True)
class SyntheticParams:
    """Parámetros de la población "normal" (todos en ms salvo que se indique)."""

    # Teclado: media por participante ~ N(mu, sd); dentro de la sesión, cada pulsación ~ N(media_part, sd_intra)
    dwell_mu: float = 95.0
    dwell_sd_between: float = 15.0
    dwell_sd_within_range: tuple = (15.0, 30.0)
    flight_mu: float = 160.0
    flight_sd_between: float = 35.0
    flight_sd_within_range: tuple = (40.0, 80.0)
    keys_range: tuple = (250, 500)  # pulsaciones por sesión

    # Mouse: velocidad media por participante en px/ms
    mouse_speed_mu: float = 0.6
    mouse_speed_sd_between: float = 0.15
    mouse_speed_cv_within: float = 0.3  # coef. de variación dentro de la sesión
    mouse_moves_range: tuple = (60, 150)

    # Señales discretas en sesiones normales (deben quedar mayormente por debajo de los umbrales)
    tab_switch_lambda: float = 0.6  # Poisson
    tab_hidden_mean_ms: float = 4_000.0  # duración media fuera de la pestaña (exponencial)
    paste_prob: float = 0.2  # probabilidad de un pegado chico (ej. una fórmula, un nombre)
    paste_chars_range: tuple = (5, 60)
    copy_lambda: float = 0.3

    # Anomalías
    dificultad: float = 2.0  # desplazamiento de `ritmo_distinto`, en desvíos poblacionales (between)

    def as_dict(self) -> dict:
        return asdict(self)


def _participant(rng: np.random.Generator, p: SyntheticParams) -> dict:
    return {
        "dwell_mean": max(40.0, rng.normal(p.dwell_mu, p.dwell_sd_between)),
        "dwell_sd": rng.uniform(*p.dwell_sd_within_range),
        "flight_mean": max(50.0, rng.normal(p.flight_mu, p.flight_sd_between)),
        "flight_sd": rng.uniform(*p.flight_sd_within_range),
        "mouse_speed": max(0.1, rng.normal(p.mouse_speed_mu, p.mouse_speed_sd_between)),
    }


def _keystrokes(rng, n_keys: int, dwell_mean, dwell_sd, flight_mean, flight_sd) -> list[dict]:
    """
    Pulsaciones sin identificar la tecla, igual que capture.ts desde el Incremento 9 (RNF01).

    Hasta la revisión del 14/10 (hallazgo M5) el generador agregaba un `code` aleatorio
    ("KeyA".."KeyZ") que la captura real ya no envía. Se quitó del evento, pero se conserva
    el sorteo que lo producía: así la secuencia de números aleatorios no cambia y los
    resultados publicados (docs/evaluacion/, cap. 18) se reproducen idénticos con las
    mismas semillas. Las métricas tampoco cambian: el generador nunca solapa teclas, de
    modo que el emparejamiento en orden de llegada (features.py) da los mismos tiempos.
    """
    events = []
    t = 0.0
    for _ in range(n_keys):
        rng.integers(0, 26)  # sorteo de la tecla, conservado solo por reproducibilidad (ver docstring)
        dwell = max(5.0, rng.normal(dwell_mean, dwell_sd))
        flight = max(5.0, rng.normal(flight_mean, flight_sd))
        events.append({"t": round(t, 1), "type": "keydown"})
        events.append({"t": round(t + dwell, 1), "type": "keyup"})
        t += dwell + flight
    return events


def _mouse(rng, n_moves: int, speed_mean: float, cv: float, span_ms: float) -> list[dict]:
    events = []
    t = float(rng.uniform(0, max(1.0, span_ms * 0.05)))
    x, y = 400.0, 300.0
    for _ in range(n_moves):
        events.append({"t": round(t, 1), "type": "mousemove", "x": round(x, 1), "y": round(y, 1)})
        dt = float(rng.uniform(100, 400))  # capture.ts throttlea mousemove a >=100 ms
        speed = max(0.01, rng.normal(speed_mean, speed_mean * cv))
        angle = float(rng.uniform(0, 2 * np.pi))
        x += speed * dt * np.cos(angle)
        y += speed * dt * np.sin(angle)
        t += dt
    if rng.random() < 0.8:
        events.append({"t": round(t, 1), "type": "click", "x": round(x, 1), "y": round(y, 1)})
    return events


def _visibility(rng, n_switches: int, hidden_mean_ms: float, span_ms: float) -> list[dict]:
    events = []
    if n_switches == 0:
        return events
    starts = np.sort(rng.uniform(0, span_ms, size=n_switches))
    last_visible = -1.0
    for s in starts:
        start = max(float(s), last_visible + 1.0)
        dur = float(rng.exponential(hidden_mean_ms))
        events.append({"t": round(start, 1), "type": "visibility", "state": "hidden"})
        events.append({"t": round(start + dur, 1), "type": "visibility", "state": "visible"})
        last_visible = start + dur
    return events


def _span(events: list[dict]) -> float:
    return max((e["t"] for e in events), default=0.0)


def generate_session(rng: np.random.Generator, params: SyntheticParams, profile: str = "normal") -> list[dict]:
    """Devuelve la lista de eventos crudos de una sesión sintética, ordenada por t."""
    if profile != "normal" and profile not in PROFILES_ANOMALOS:
        raise ValueError(f"Perfil desconocido: {profile}")

    part = _participant(rng, params)
    n_keys = int(rng.integers(*params.keys_range))
    n_moves = int(rng.integers(*params.mouse_moves_range))
    n_tabs = int(rng.poisson(params.tab_switch_lambda))
    hidden_mean = params.tab_hidden_mean_ms

    if profile == "tecleo_automatizado":
        part["dwell_sd"] = float(rng.uniform(0.5, 3.0))
        part["flight_sd"] = float(rng.uniform(0.5, 5.0))
    elif profile == "ritmo_distinto":
        # Misma distribución entre participantes que la población normal, desplazada
        # k desvíos (between) en las tres dimensiones. Con k = 0 el perfil es
        # indistinguible de lo normal (AUC esperado ~0,5): el desplazamiento se suma
        # a la variación entre participantes en vez de reemplazarla (ver bitácora,
        # Incremento 6: la primera versión fijaba la media en mu + k*sd y producía
        # un AUC < 0,5 con k chico, un artefacto del generador).
        k = params.dificultad
        part["dwell_mean"] += k * params.dwell_sd_between
        part["flight_mean"] += k * params.flight_sd_between
        part["mouse_speed"] += k * params.mouse_speed_sd_between
    elif profile == "pegado_masivo":
        n_keys = max(30, int(n_keys * 0.3))  # se tipea poco: la mayor parte del texto llega pegada
    elif profile == "cambio_pestana":
        n_tabs = int(rng.integers(6, 13))
        hidden_mean = float(rng.uniform(5_000, 15_000))

    events = _keystrokes(rng, n_keys, part["dwell_mean"], part["dwell_sd"], part["flight_mean"], part["flight_sd"])
    span = _span(events)
    events += _mouse(rng, n_moves, part["mouse_speed"], params.mouse_speed_cv_within, span)
    events += _visibility(rng, n_tabs, hidden_mean, span)

    if profile == "pegado_masivo":
        n_pastes = int(rng.integers(1, 4))
        total = float(rng.uniform(400, 2000))
        for chars in rng.multinomial(int(total), [1 / n_pastes] * n_pastes):
            events.append({"t": round(float(rng.uniform(0, span)), 1), "type": "paste", "chars": int(chars)})
    elif rng.random() < params.paste_prob:
        events.append({"t": round(float(rng.uniform(0, span)), 1), "type": "paste", "chars": int(rng.integers(*params.paste_chars_range))})

    for _ in range(int(rng.poisson(params.copy_lambda))):
        events.append({"t": round(float(rng.uniform(0, span)), 1), "type": "copy"})

    events.sort(key=lambda e: e["t"])
    return events
