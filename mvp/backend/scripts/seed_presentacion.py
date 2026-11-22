"""
Datos de DEMOSTRACIÓN para la presentación final: deja el panel de un docente "con uso",
como si hubiera tomado varias evaluaciones a lo largo del cuatrimestre.

Qué carga (fechas relativas al momento en que se corre el script, ver --ancla):

  1. Parcial 1 · Bases de Datos I — Comisión mañana     hace 45 días, cerrada, todo revisado
  2. Parcial 1 · Bases de Datos I — Comisión noche      hace 45 días, cerrada, todo revisado
                                                         (incluye una validación adicional ya resuelta)
  3. TP integrador · Ingeniería de Software II           hace 24 días, cerrada, A LIBRO ABIERTO
                                                         (pegar y otras pestañas permitidos: indicadores
                                                         "permitidos por las reglas")
  4. Parcial 2 · Bases de Datos I — Comisión mañana     hace 3 días, cerrada, revisión A MEDIAS
                                                         (una validación pendiente, varias sin revisar,
                                                         política editada: versión 2, una sesión con
                                                         captura incompleta)
  5. Parcial 2 · Bases de Datos I — Comisión noche      hace 3 días, cerrada, SIN revisar
  6. Recuperatorio · Bases de Datos I                    HOY, ABIERTA, 19 entregas: al rendir una más
                                                         en vivo llega a 20 y "Cerrar y analizar" ya
                                                         ejecuta el modelo poblacional

Todo pasa por la API real (crear evaluación -> /sessions/start -> /events -> /end ->
/exams/{id}/cerrar -> /reviews), así que métricas, indicadores, cierre y modelo
poblacional los calcula el pipeline de verdad. Después se corren las fechas en la base
para que cada evaluación quede en su día (la API siempre usa "ahora").

Las sesiones son SINTÉTICAS (app/evaluation/synthetic.py). Los códigos de participante
(P-101, P-102, ...) y las respuestas son inventados: no hay datos de personas reales.

Uso local (desde mvp/backend, sin necesidad de levantar el backend):

    python -m scripts.seed_presentacion                       # usa ./impronta.db
    python -m scripts.seed_presentacion --reiniciar           # borra antes las evaluaciones de la demo
    python -m scripts.seed_presentacion --database-url sqlite:///./impronta_demo.db

Contra la plataforma desplegada (p. ej. Render), con acceso a su base para las fechas:

    python -m scripts.seed_presentacion --api https://improntia-api.onrender.com \\
        --database-url "$DATABASE_URL_EXTERNA"      # la clave del docente la pide por teclado

- El docente tiene que existir (en producción lo crea SEED_TEACHERS); el script no lo crea.
- Antes de empezar espera a que la API despierte (/health). Los errores transitorios (5xx,
  cortes, timeouts) se reintentan; los lotes de eventos y el cierre son idempotentes.
- Sin --database-url la carga funciona igual, pero las fechas quedan en "hoy" (avisa).
- --reiniciar y --solo-borrar eliminan SOLO las evaluaciones de la demo (nombre de la demo y mayoría de sesiones sintéticas) de ese
  docente; en la plataforma desplegada piden confirmación (--si-borrar <email del docente>).
- --escala: `completa` envía las ~5.000-8.000 pulsaciones/eventos de cada sesión (~155 MB en
  SQLite); `liviana` conserva 1 de cada 5 pulsaciones con sus tiempos y todo lo demás (ver
  `aligerar`): misma historia, mismas duraciones e indicadores, ~5 veces menos filas. Es el
  default contra la nube o PostgreSQL (`auto`).
- Cada sesión lleva en su contexto {"origen": "demo_sintetica"}; nunca lleva
  `condicion_simulacion`, así que no entra en las exportaciones de simulaciones.
"""
from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402

DEFAULT_EMAIL = "docente@uade.edu.ar"
DEFAULT_PASSWORD = "1234"
ART = timezone(timedelta(hours=-3))  # Argentina, sin horario de verano
TODAS_LAS_SENALES = ["keyboard", "mouse", "scroll", "visibility", "clipboard"]

# --------------------------------------------------------------------------------------
# Textos de las evaluaciones
# --------------------------------------------------------------------------------------

INFO_TEXT = (
    "Durante esta evaluación la plataforma registra señales de interacción (ritmo de tecleo, "
    "movimiento del mouse, cambios de pestaña y uso del portapapeles) para ayudar al docente a "
    "priorizar qué entregas revisar con más atención. No se registra qué teclas presionás ni el "
    "texto que pegás. Ninguna señal es una conclusión sobre tu conducta: cualquier decisión la "
    "toma el docente después de revisar la evidencia."
)

RULES_CERRADO = (
    "Examen individual a libro cerrado. No está permitido consultar apuntes, otras pestañas ni "
    "herramientas externas. Respondé con tus palabras en el cuadro de respuesta."
)

RULES_ABIERTO = (
    "Actividad individual a libro abierto: podés consultar el material de la cátedra, la "
    "documentación de tu TP y otras pestañas, y pegar fragmentos propios o citas (indicando la "
    "fuente). La respuesta tiene que ser tuya."
)

PROMPT_P1 = (
    "Normalización. Dado el esquema VENTAS(nro_factura, fecha, cod_cliente, nombre_cliente, "
    "cod_producto, descripcion, cantidad, precio_unitario):\n"
    "a) Identificá las dependencias funcionales.\n"
    "b) Indicá en qué forma normal está y por qué.\n"
    "c) Llevalo a 3FN justificando cada descomposición."
)

PROMPT_P2 = (
    "Transacciones y concurrencia. Dos cajeros actualizan al mismo tiempo el saldo de una misma "
    "cuenta: T1 lee el saldo, le suma un depósito y lo escribe; T2 lee el saldo, le resta una "
    "extracción y lo escribe.\n"
    "a) ¿Qué anomalía puede ocurrir? Mostrala con una planificación concreta.\n"
    "b) ¿Qué nivel de aislamiento la evita y con qué costo?\n"
    "c) Escribí la sentencia SQL que usarías para evitarla sin cambiar el nivel de aislamiento."
)

PROMPT_TP = (
    "Arquitectura de tu TP integrador. Describí el estilo arquitectónico que eligieron, dos "
    "decisiones de diseño importantes (con la alternativa que descartaron y por qué) y cómo "
    "validaron al menos un requerimiento no funcional."
)

PROMPT_RECU = (
    "Modelo entidad-relación. Una biblioteca presta ejemplares de libros a socios; cada libro "
    "puede tener varios autores y varios ejemplares, y un socio puede tener hasta tres préstamos "
    "activos.\n"
    "a) Proponé el DER con sus cardinalidades.\n"
    "b) Pasalo al modelo relacional indicando claves primarias y foráneas.\n"
    "c) ¿Dónde y cómo controlarías la restricción de los tres préstamos?"
)

# Respuestas: se arman combinando un fragmento de cada grupo, para que no haya dos iguales.
RESP_P1 = [
    [
        "Las dependencias funcionales que identifico son: nro_factura -> fecha, cod_cliente; "
        "cod_cliente -> nombre_cliente; cod_producto -> descripcion, precio_unitario; y "
        "(nro_factura, cod_producto) -> cantidad.",
        "a) DF: nro_factura determina fecha y cod_cliente. cod_cliente determina nombre_cliente. "
        "cod_producto determina descripcion y precio_unitario. La cantidad depende de la factura y "
        "del producto juntos.",
        "Primero busco la clave: es (nro_factura, cod_producto), porque una factura tiene muchos "
        "productos. Con eso las DF son nro_factura -> fecha, cod_cliente; cod_cliente -> "
        "nombre_cliente; cod_producto -> descripcion, precio_unitario; clave -> cantidad.",
    ],
    [
        "b) Está en 1FN pero no en 2FN, porque hay atributos que dependen de una parte de la clave "
        "(fecha depende solo de nro_factura y descripcion solo de cod_producto).",
        "b) La relación está en 1FN: todos los atributos son atómicos. No cumple 2FN porque hay "
        "dependencias parciales respecto de la clave compuesta.",
        "b) 1FN. Hay dependencias parciales (descripcion y precio dependen solo del producto) y "
        "además una transitiva (nro_factura -> cod_cliente -> nombre_cliente).",
    ],
    [
        "c) Para 2FN separo FACTURA(nro_factura, fecha, cod_cliente, nombre_cliente), "
        "PRODUCTO(cod_producto, descripcion, precio_unitario) y DETALLE(nro_factura, cod_producto, "
        "cantidad). Para 3FN saco la transitiva de FACTURA: CLIENTE(cod_cliente, nombre_cliente) y "
        "FACTURA(nro_factura, fecha, cod_cliente).",
        "c) Descompongo en CLIENTE(cod_cliente, nombre_cliente), FACTURA(nro_factura, fecha, "
        "cod_cliente FK), PRODUCTO(cod_producto, descripcion, precio_unitario) y "
        "LINEA_FACTURA(nro_factura FK, cod_producto FK, cantidad). Cada paso es sin pérdida porque "
        "el atributo común es clave en una de las dos partes.",
        "c) Quedan cuatro tablas: Cliente, Factura, Producto y DetalleFactura. Aclaro que si el "
        "precio puede cambiar en el tiempo convendría guardar el precio de venta en el detalle, "
        "pero con las DF dadas va en Producto.",
    ],
]

RESP_P2 = [
    [
        "a) Puede ocurrir una actualización perdida: T1 lee 1000, T2 lee 1000, T1 escribe 1500 y "
        "T2 escribe 800. El depósito de T1 se pierde.",
        "a) La anomalía es lost update. Planificación: R1(saldo) R2(saldo) W1(saldo) C1 W2(saldo) "
        "C2. La escritura de T2 pisa la de T1.",
        "a) Si las dos leen antes de que alguna escriba, la segunda escritura sobrescribe a la "
        "primera (actualización perdida).",
    ],
    [
        "b) Se evita con SERIALIZABLE (o REPEATABLE READ en motores que detectan el conflicto). El "
        "costo es más bloqueos o más transacciones abortadas que hay que reintentar.",
        "b) Con nivel REPEATABLE READ o SERIALIZABLE. Baja la concurrencia y aparecen reintentos.",
        "b) El nivel serializable la evita. A cambio, más esperas por bloqueos o rollbacks por "
        "conflicto de serialización.",
    ],
    [
        "c) UPDATE cuenta SET saldo = saldo + :monto WHERE id = :id; así la lectura y la escritura "
        "son atómicas en una sola sentencia.",
        "c) SELECT saldo FROM cuenta WHERE id = :id FOR UPDATE; y después el UPDATE dentro de la "
        "misma transacción. El FOR UPDATE bloquea la fila hasta el commit.",
        "c) Usaría UPDATE cuenta SET saldo = saldo - :monto WHERE id = :id AND saldo >= :monto, "
        "que además evita saldo negativo.",
    ],
]

RESP_TP = [
    [
        "Elegimos una arquitectura en capas (presentación, servicios y datos) con una API REST, "
        "porque el equipo ya la conocía y el dominio no justificaba microservicios.",
        "Usamos un monolito modular: un único despliegue pero con módulos separados por dominio "
        "(turnos, pacientes y facturación) que se comunican por interfaces.",
        "La solución es cliente-servidor: una SPA en React y un backend en FastAPI con PostgreSQL.",
    ],
    [
        "Una decisión fue usar PostgreSQL en vez de MongoDB: los datos son muy relacionales y "
        "necesitábamos transacciones. Otra fue autenticar con JWT en lugar de sesiones en el "
        "servidor, para no depender de estado compartido.",
        "Descartamos los microservicios por el costo operativo para un equipo de cuatro. También "
        "decidimos validar en el backend y no solo en el front, aunque duplicara código.",
        "Elegimos colas de mensajes para las notificaciones (alternativa: llamadas síncronas) para "
        "que una caída del servicio de mails no bloquee la reserva.",
    ],
    [
        "Para el RNF de rendimiento hicimos una prueba de carga con 200 usuarios concurrentes y el "
        "p95 quedó en 420 ms, por debajo de los 800 ms pedidos.",
        "Validamos usabilidad con cinco usuarios de prueba y la tarea principal se completó en "
        "menos de dos minutos en promedio.",
        "Para disponibilidad configuramos health checks y reinicio automático; en dos semanas de "
        "prueba no hubo caídas de más de un minuto.",
    ],
]

RESP_RECU = [
    [
        "a) Entidades: LIBRO, AUTOR, EJEMPLAR, SOCIO y PRESTAMO. LIBRO-AUTOR es N:M, LIBRO-EJEMPLAR "
        "1:N, y PRESTAMO relaciona un SOCIO con un EJEMPLAR.",
        "a) DER: Libro (isbn, titulo) N:M Autor; Libro 1:N Ejemplar; Socio 1:N Préstamo N:1 "
        "Ejemplar.",
        "a) Tomo Préstamo como entidad débil entre Socio y Ejemplar, con fecha de préstamo y de "
        "devolución. Libro y Autor quedan N:M.",
    ],
    [
        "b) LIBRO(isbn PK, titulo), AUTOR(id_autor PK, nombre), LIBRO_AUTOR(isbn FK, id_autor FK), "
        "EJEMPLAR(id_ejemplar PK, isbn FK), SOCIO(nro_socio PK, nombre), PRESTAMO(id PK, nro_socio "
        "FK, id_ejemplar FK, fecha_desde, fecha_devolucion).",
        "b) La N:M genera la tabla LibroAutor con clave compuesta. Ejemplar lleva el isbn como FK y "
        "Prestamo lleva las FK de socio y de ejemplar.",
        "b) Siete tablas no, seis: Libro, Autor, LibroAutor, Ejemplar, Socio y Prestamo, con las FK "
        "correspondientes.",
    ],
    [
        "c) La restricción de tres préstamos activos no se puede expresar con cardinalidades; la "
        "controlaría con un trigger BEFORE INSERT en PRESTAMO que cuente los préstamos sin fecha "
        "de devolución del socio.",
        "c) Con un trigger o en la capa de servicio, contando los préstamos activos antes de "
        "insertar uno nuevo, dentro de la misma transacción.",
        "c) La pondría en un procedimiento almacenado que registre el préstamo y valide el límite.",
    ],
]


# --------------------------------------------------------------------------------------
# Plan de la demo
# --------------------------------------------------------------------------------------

@dataclass
class PlanEvaluacion:
    clave: str
    nombre: str
    consigna: str
    respuestas: list
    dias_atras: int
    hora_local: int  # hora de inicio (Argentina)
    normales: int
    anomalas: dict  # perfil -> cantidad
    abierta: bool = False  # True: queda abierta (sin cierre ni modelo)
    libro_abierto: bool = False
    politica_v2: bool = False  # se edita la política antes de rendir (muestra el versionado)
    captura_incompleta: int = 0  # cuántas sesiones normales llegan con una falla de sincronización
    revision: str = "completa"  # "completa" | "parcial" | "ninguna"
    primer_participante: int = 101
    semilla: int = 0
    reviews_hechas: list = field(default_factory=list)


PLAN = [
    PlanEvaluacion("p1m", "Parcial 1 · Bases de Datos I — Comisión mañana", PROMPT_P1, RESP_P1,
                   dias_atras=45, hora_local=9, normales=24,
                   anomalas={"pegado_masivo": 1, "cambio_pestana": 1, "tecleo_automatizado": 1, "ritmo_distinto": 1},
                   primer_participante=101, semilla=11),
    PlanEvaluacion("p1n", "Parcial 1 · Bases de Datos I — Comisión noche", PROMPT_P1, RESP_P1,
                   dias_atras=45, hora_local=19, normales=21,
                   anomalas={"pegado_masivo": 1, "cambio_pestana": 1, "ritmo_distinto": 1},
                   primer_participante=201, semilla=12),
    PlanEvaluacion("tp", "TP integrador · Ingeniería de Software II", PROMPT_TP, RESP_TP,
                   dias_atras=24, hora_local=18, normales=16,
                   anomalas={"pegado_masivo": 3, "cambio_pestana": 2, "ritmo_distinto": 1},
                   libro_abierto=True, primer_participante=301, semilla=13),
    PlanEvaluacion("p2m", "Parcial 2 · Bases de Datos I — Comisión mañana", PROMPT_P2, RESP_P2,
                   dias_atras=3, hora_local=9, normales=25,
                   anomalas={"pegado_masivo": 2, "cambio_pestana": 1, "tecleo_automatizado": 1, "ritmo_distinto": 1},
                   politica_v2=True, captura_incompleta=1, revision="parcial",
                   primer_participante=101, semilla=14),
    PlanEvaluacion("p2n", "Parcial 2 · Bases de Datos I — Comisión noche", PROMPT_P2, RESP_P2,
                   dias_atras=3, hora_local=19, normales=22,
                   anomalas={"pegado_masivo": 1, "cambio_pestana": 2, "ritmo_distinto": 1},
                   revision="ninguna", primer_participante=201, semilla=15),
    PlanEvaluacion("recu", "Recuperatorio · Bases de Datos I", PROMPT_RECU, RESP_RECU,
                   dias_atras=0, hora_local=-1, normales=17,
                   anomalas={"pegado_masivo": 1, "cambio_pestana": 1},
                   abierta=True, revision="ninguna", primer_participante=401, semilla=16),
]

# Notas de revisión según el indicador principal de la sesión.
NOTAS = {
    "paste_volume_alto": [
        "Revisé la entrega: el bloque pegado es la definición del apunte de la cátedra y está "
        "citada. El resto de la respuesta es propio. Sin observaciones.",
        "El texto pegado es un borrador que el estudiante escribió en otra ventana por miedo a "
        "perderlo (lo mostró). La redacción coincide con su estilo en los TP. Sin observaciones.",
    ],
    "cambios_pestana_frecuentes": [
        "Hablé con el estudiante: se le cortaba el wifi y cambiaba de ventana para reconectar. "
        "La respuesta es consistente con su desempeño en clase. Sin observaciones.",
    ],
    "perdida_foco_prolongada": [
        "Tiempo fuera de la pestaña alto. El estudiante avisó durante el examen que tenía que "
        "atender una llamada familiar; quedó registrado en el aula. Sin observaciones.",
    ],
    "ritmo_tecleo_atipico": [
        "Ritmo de tecleo muy uniforme. Revisé la respuesta junto con el indicador y la contrasté "
        "con la defensa oral: explicó todo con solvencia. Sin observaciones.",
    ],
    "atipico_modelo_poblacional": [
        "El modelo la marca como atípica frente a la comisión, pero no hay otros indicios y la "
        "respuesta es coherente con sus parciales anteriores. Sin observaciones.",
        "Ritmo distinto al del resto del grupo; el estudiante usa un teclado externo con otra "
        "distribución. Sin observaciones.",
    ],
    None: ["Revisada. Sin observaciones."],
}

NOTA_VALIDACION = (
    "Antes de publicar la nota pido una instancia oral breve (15 min) para que explique "
    "la resolución. Coordinar horario con el estudiante."
)
NOTA_VALIDACION_RESUELTA = (
    "Coloquio oral realizado: explicó el razonamiento paso a paso y respondió las "
    "repreguntas. Se cierra la revisión sin observaciones."
)

KIND_PRIORIDAD = [
    "paste_volume_alto", "perdida_foco_prolongada", "cambios_pestana_frecuentes",
    "ritmo_tecleo_atipico", "atipico_modelo_poblacional",
]


# --------------------------------------------------------------------------------------
# Volumen: escala de la demo
# --------------------------------------------------------------------------------------

# Pulsaciones que se conservan: 1 de cada `k`. Ver `aligerar` y docs en el encabezado.
ESCALAS = {"completa": 1, "liviana": 5}


def aligerar(events: list[dict], cada: int) -> list[dict]:
    """
    Escala liviana: conserva 1 de cada `cada` pulsaciones (el par keydown/keyup completo, con
    sus tiempos originales) y TODOS los demás eventos.

    Por qué así y no generando menos pulsaciones: la sesión se genera igual que en la escala
    completa (mismo sorteo, mismas respuestas, mismos perfiles) y recién después se aligera,
    de modo que
      - la duración no cambia: las pulsaciones que quedan siguen repartidas a lo largo de toda
        la sesión (generar menos teclas acortaba el examen a 2-3 minutos);
      - la duración de cada pulsación (dwell) y su variabilidad no cambian: el perfil
        `tecleo_automatizado` sigue disparando `ritmo_tecleo_atipico` y las normales no;
      - pegados, cambios de pestaña, copias, mouse y la falla de sincronización son los mismos
        eventos: los indicadores por reglas son idénticos a los de la escala completa;
      - el tiempo entre teclas (flight) pasa a ser el de `cada` pulsaciones (~1 s en vez de
        ~0,2 s, como alguien que escribe pensando). Cambia igual para todas las sesiones, así
        que `ritmo_distinto` sigue igual de separado del resto para el modelo poblacional.
    Lo único visiblemente distinto es la cantidad de teclas de la sesión (≈ 1/`cada`).
    """
    if cada <= 1:
        return events
    out, n, conservar_keyup = [], 0, False
    for e in events:  # ordenados por t; el generador nunca solapa teclas
        if e["type"] == "keydown":
            conservar_keyup = n % cada == 0
            n += 1
            if conservar_keyup:
                out.append(e)
        elif e["type"] == "keyup":
            if conservar_keyup:
                out.append(e)
                conservar_keyup = False
        else:
            out.append(e)
    return out


# --------------------------------------------------------------------------------------
# HTTP: reintentos, API que despierta, operaciones no idempotentes
# --------------------------------------------------------------------------------------

class Ambiguo(Exception):
    """Un POST no idempotente pudo haberse aplicado o no (se cortó la respuesta)."""


class Api:
    """
    Envoltorio del cliente HTTP (httpx.Client contra la API desplegada, o el TestClient en
    modo local) con reintentos ante errores transitorios: 5xx, 429, desconexiones y timeouts.

    Los endpoints idempotentes se reintentan sin más (lotes de eventos: el servidor descarta un
    `seq` ya aplicado; /end y /cerrar son idempotentes; los GET y DELETE también). Un POST no
    idempotente (crear evaluación o sesión, registrar una revisión) solo se reintenta solo si
    el pedido seguro no llegó (no se pudo conectar); si se cortó después de enviarlo se levanta
    `Ambiguo` y quien llama verifica antes de repetirlo.
    """

    TRANSITORIOS = {429, 500, 502, 503, 504}

    def __init__(self, client, reintentos: int = 6, espera: float = 2.0, verbose: bool = True):
        self.client = client
        self.reintentos = reintentos
        self.espera = espera
        self.verbose = verbose
        self.pedidos = 0
        self.reintentados = 0

    def _dormir(self, intento: int, motivo: str, what: str) -> None:
        import time
        pausa = min(30.0, self.espera * (2 ** (intento - 1)))
        self.reintentados += 1
        if self.verbose:
            print(f"    ! {what}: {motivo}; reintento {intento}/{self.reintentos - 1} en {pausa:.0f} s", flush=True)
        time.sleep(pausa)

    def request(self, method: str, url: str, *, what: str, idempotente: bool = True, **kw):
        import httpx
        for intento in range(1, self.reintentos + 1):
            ultimo = intento == self.reintentos
            self.pedidos += 1
            try:
                r = self.client.request(method, url, **kw)
            except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout) as exc:
                # El pedido no salió: se puede repetir aunque no sea idempotente.
                if ultimo:
                    raise SystemExit(f"Error en {what}: no se pudo conectar con la API ({type(exc).__name__}: {exc}).")
                self._dormir(intento, type(exc).__name__, what)
                continue
            except httpx.TransportError as exc:  # timeout de lectura, conexión cortada, ...
                if not idempotente:
                    raise Ambiguo(what) from exc
                if ultimo:
                    raise SystemExit(f"Error en {what}: {type(exc).__name__}: {exc}")
                self._dormir(intento, type(exc).__name__, what)
                continue
            if r.status_code in self.TRANSITORIOS:
                if not idempotente:
                    raise Ambiguo(what)
                if not ultimo:
                    self._dormir(intento, f"HTTP {r.status_code}", what)
                    continue
            return _check(r, what)
        raise AssertionError("inalcanzable")

    def get(self, url, *, what, **kw):
        return self.request("GET", url, what=what, **kw)

    def post(self, url, *, what, idempotente=True, **kw):
        return self.request("POST", url, what=what, idempotente=idempotente, **kw)

    def delete(self, url, *, what, **kw):
        return self.request("DELETE", url, what=what, **kw)


def _check(r, what: str):
    if r.status_code >= 400:
        raise SystemExit(f"Error en {what}: HTTP {r.status_code} {r.text[:300]}")
    return r


def esperar_api(client, max_espera_s: float = 240.0) -> dict:
    """
    Pide /health hasta que responda. Los servicios gratuitos (Render free) apagan la API tras
    ~15 min sin uso y tardan alrededor de un minuto en despertarla: mientras tanto el proxy
    responde 502/503 o deja el pedido esperando.
    """
    import time

    import httpx
    t0 = time.monotonic()
    avisado = False
    while True:
        detalle = ""
        try:
            r = client.get("/health", timeout=httpx.Timeout(90.0, connect=20.0))
            if r.status_code == 200:
                return r.json()
            if r.status_code == 404:
                raise SystemExit(f"La URL de --api no parece ser la API de ImprontIA (/health respondió 404): {client.base_url}")
            detalle = f"HTTP {r.status_code}"
        except httpx.TransportError as exc:
            detalle = type(exc).__name__
        transcurrido = time.monotonic() - t0
        if transcurrido > max_espera_s:
            raise SystemExit(f"La API no respondió en {max_espera_s:.0f} s ({detalle}). Revisá la URL y que el "
                             "servicio esté activo en el panel del proveedor.")
        if not avisado:
            print("Esperando que la API despierte (en el plan gratuito puede tardar ~1 minuto)...", flush=True)
            avisado = True
        time.sleep(5)


# --------------------------------------------------------------------------------------
# Carga
# --------------------------------------------------------------------------------------

def _respuesta(rng: np.random.Generator, grupos: list) -> str:
    return "\n\n".join(str(g[int(rng.integers(0, len(g)))]) for g in grupos)


def _respuesta_corta(rng: np.random.Generator, grupos: list) -> str:
    # Entrega incompleta (alguien que no llegó a terminar): solo los primeros puntos.
    n = int(rng.integers(1, len(grupos)))
    return _respuesta(rng, grupos[:n])


def _rendir(api: Api, join_code: str, participante: str, events: list, respuesta: str,
            lote: int, contexto: dict) -> dict:
    try:
        s = api.post("/sessions/start", what="iniciar sesión", idempotente=False, json={
            "exam_code": join_code, "participant_id": participante, "session_type": "exam",
            "context": contexto, "consent_given": True,
        }).json()
    except Ambiguo:
        # Si la primera sesión llegó a crearse queda activa y sin eventos: se elimina al
        # terminar de cargar la evaluación (ver `_limpiar_huerfanas`).
        s = api.post("/sessions/start", what="iniciar sesión (reintento)", json={
            "exam_code": join_code, "participant_id": participante, "session_type": "exam",
            "context": contexto, "consent_given": True,
        }).json()
    sid, headers = s["session_id"], {"X-Session-Token": s["session_token"]}
    for seq, i in enumerate(range(0, len(events), lote), start=1):
        # Idempotente: un lote repetido con el mismo `seq` no se reinserta.
        api.post(f"/sessions/{sid}/events", what="enviar eventos", headers=headers,
                 json={"seq": seq, "events": events[i:i + lote]})
    end = api.post(f"/sessions/{sid}/end", what="entregar", headers=headers, json={"respuesta": respuesta})
    return {"session_id": sid, **end.json()}


def _crear_evaluacion(api: Api, auth: dict, body: dict) -> dict:
    try:
        return api.post("/exams", what="crear evaluación", idempotente=False, json=body, headers=auth).json()
    except Ambiguo:
        # ¿Llegó a crearse? Se busca una evaluación con ese nombre y sin sesiones todavía.
        for e in api.get("/exams", what="listar evaluaciones", headers=auth).json():
            if e["name"] == body["name"] and not api.get(
                    "/sessions", what="listar sesiones", params={"exam_id": e["id"]}, headers=auth).json():
                return e
        return api.post("/exams", what="crear evaluación (reintento)", json=body, headers=auth).json()


def _post_revision(api: Api, auth: dict, session_id: str, body: dict) -> dict:
    try:
        return api.post(f"/sessions/{session_id}/reviews", what="revisar", idempotente=False,
                        json=body, headers=auth).json()
    except Ambiguo:
        det = api.get(f"/sessions/{session_id}", what="detalle de sesión", headers=auth).json()
        for r in det["reviews"]:
            if r["action"] == body["action"] and r["notes"] == body["notes"]:
                return r
        return api.post(f"/sessions/{session_id}/reviews", what="revisar (reintento)", json=body, headers=auth).json()


def _limpiar_huerfanas(api: Api, auth: dict, exam_id: str, propias: set) -> int:
    """Sesiones que quedaron de un /sessions/start reintentado: se eliminan."""
    n = 0
    for s in api.get("/sessions", what="listar sesiones", params={"exam_id": exam_id}, headers=auth).json():
        if s["id"] not in propias:
            api.delete(f"/sessions/{s['id']}", what="eliminar sesión huérfana", headers=auth)
            n += 1
    return n


def preparar_sesiones(plan: PlanEvaluacion, cada: int) -> list[dict]:
    """Genera (sin enviar) las sesiones de una evaluación. Determinístico: depende solo de la
    semilla del plan; la escala se aplica después de generar (ver `aligerar`)."""
    from app.evaluation.synthetic import SyntheticParams, generate_session

    rng = np.random.default_rng(plan.semilla)
    # Respuestas más largas que las de la evaluación sintética (una consigna de desarrollo).
    params = SyntheticParams(keys_range=(1500, 3000), mouse_moves_range=(200, 450), dificultad=3.0)

    perfiles = ["normal"] * plan.normales
    for perfil, n in plan.anomalas.items():
        perfiles += [perfil] * n
    rng.shuffle(perfiles)

    sesiones = []
    incompletas = plan.captura_incompleta
    for i, perfil in enumerate(perfiles):
        events = generate_session(rng, params, perfil)
        if perfil == "normal" and incompletas > 0 and i > 3:
            t = round(max(e["t"] for e in events) * 0.6, 1)
            events.append({"t": t, "type": "sync_failure", "failed_attempts": 5, "duration_ms": 48_000.0})
            events.sort(key=lambda e: e["t"])
            incompletas -= 1
        respuesta = (_respuesta_corta(rng, plan.respuestas) if rng.random() < 0.12
                     else _respuesta(rng, plan.respuestas))
        events = aligerar(events, cada)
        sesiones.append({
            "participante": f"P-{plan.primer_participante + i:03d}",
            "perfil": perfil,
            "events": events,
            "respuesta": respuesta,
            "span_ms": max((e["t"] for e in events), default=0.0),
        })
    return sesiones


def cargar_evaluacion(api: Api, auth: dict, plan: PlanEvaluacion, cada: int = 1, lote: int = 2500,
                      paralelo: int = 1, nombre: Optional[str] = None, escala: str = "completa") -> dict:
    body = {
        "name": nombre or plan.nombre,
        "prompt_text": plan.consigna,
        "info_text": INFO_TEXT,
        "rules_text": RULES_ABIERTO if plan.libro_abierto else RULES_CERRADO,
        "allowed_signals": TODAS_LAS_SENALES,
        "permite_pegado": plan.libro_abierto,
        "permite_otras_pestanas": plan.libro_abierto,
        "retencion_dias": 180,
    }
    exam = _crear_evaluacion(api, auth, body)
    if plan.politica_v2 and exam.get("policy_version", 1) < 2:
        # Versión 2: se aclara el texto informativo antes de rendir (RNF04: queda la v1 intacta).
        v2 = {k: body[k] for k in ("info_text", "rules_text", "allowed_signals", "permite_pegado",
                                   "permite_otras_pestanas", "retencion_dias")}
        v2["rules_text"] = RULES_CERRADO + " Tenés 45 minutos. Podés usar una hoja en blanco para borradores."
        try:
            api.post(f"/exams/{exam['id']}/policy", what="editar política", idempotente=False, json=v2, headers=auth)
        except Ambiguo:
            actual = api.get(f"/exams/{exam['id']}", what="leer evaluación", headers=auth).json()
            if actual["policy_version"] < 2:
                api.post(f"/exams/{exam['id']}/policy", what="editar política (reintento)", json=v2, headers=auth)

    preparadas = preparar_sesiones(plan, cada)
    # Marca de datos de demostración en el contexto de cada sesión (no lo ve el estudiante ni
    # cambia el análisis): permite distinguirlas en la base de las sesiones reales.
    contexto = {"origen": "demo_sintetica", "generador": "scripts.seed_presentacion", "escala": escala}

    def enviar(p: dict) -> dict:
        res = _rendir(api, exam["join_code"], p["participante"], p["events"], p["respuesta"], lote, contexto)
        return {"id": res["session_id"], "perfil": p["perfil"], "span_ms": p["span_ms"],
                "eventos": len(p["events"])}

    if paralelo > 1:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=paralelo) as pool:
            sesiones = list(pool.map(enviar, preparadas))  # conserva el orden de participantes
    else:
        sesiones = [enviar(p) for p in preparadas]

    huerfanas = _limpiar_huerfanas(api, auth, exam["id"], {s["id"] for s in sesiones})
    if huerfanas:
        print(f"    (se eliminaron {huerfanas} sesiones huérfanas de reintentos)")
    if not plan.abierta:
        api.post(f"/exams/{exam['id']}/cerrar", what="cerrar evaluación", headers=auth)
    return {"exam": exam, "sesiones": sesiones}


def _kind_principal(indicators: list) -> tuple[Optional[str], list]:
    prioritarios = [i for i in indicators if i["kind"] != "captura_incompleta"
                    and not (i.get("explanation") or {}).get("permitido_por_reglas")]
    for kind in KIND_PRIORIDAD:
        for ind in prioritarios:
            if ind["kind"] == kind:
                return kind, [i["id"] for i in prioritarios]
    return None, [i["id"] for i in prioritarios]


def revisar(api: Api, auth: dict, plan: PlanEvaluacion, exam_id: str) -> list:
    """Registra revisiones docentes. Devuelve [(review_id, desfase_en_horas)] para fecharlas."""
    if plan.revision == "ninguna":
        return []
    rng = np.random.default_rng(plan.semilla + 1000)
    marcadas = api.get("/sessions", what="listar sesiones", params={"exam_id": exam_id, "needs_review": True},
                       headers=auth).json()
    marcadas.sort(key=lambda s: s["participant_id"])
    hechas = []

    def registrar(sid: str, action: str, notes: str, ids: list, horas: float) -> None:
        r = _post_revision(api, auth, sid, {"action": action, "notes": notes, "indicator_ids": ids})
        hechas.append((r["id"], horas))

    for idx, s in enumerate(marcadas):
        det = api.get(f"/sessions/{s['id']}", what="detalle de sesión", headers=auth).json()
        kind, ids = _kind_principal(det["indicators"])
        notas = NOTAS.get(kind, NOTAS[None])
        nota = notas[int(rng.integers(0, len(notas)))]
        horas = 20 + idx * 3 + float(rng.uniform(0, 2))  # al día siguiente del examen, en tandas

        if plan.revision == "parcial":
            # Parcial 2 (hace 3 días): la primera mitad revisada, una con validación pendiente,
            # el resto sin revisar para mostrar la revisión en vivo.
            if idx < len(marcadas) // 2 - 1:
                registrar(s["id"], "marked_reviewed", nota, ids, horas)
            elif idx == len(marcadas) // 2 - 1:
                registrar(s["id"], "additional_validation", NOTA_VALIDACION, ids, horas)
            continue

        # Revisión completa. En la primera sesión de cada evaluación con un indicio fuerte, se
        # pide validación adicional y días después se cierra (muestra el historial).
        if idx == 0 and kind in ("paste_volume_alto", "ritmo_tecleo_atipico"):
            registrar(s["id"], "additional_validation", NOTA_VALIDACION, ids, horas)
            registrar(s["id"], "marked_reviewed", NOTA_VALIDACION_RESUELTA, [], horas + 24 * 4)
        else:
            registrar(s["id"], "marked_reviewed", nota, ids, horas)
    return hechas


# --------------------------------------------------------------------------------------
# Fechas (acceso directo a la base)
# --------------------------------------------------------------------------------------

def _inicio_utc(ancla: datetime, plan: PlanEvaluacion) -> datetime:
    """Inicio del examen en UTC naive (como se guarda en la base)."""
    local = ancla.astimezone(ART)
    if plan.hora_local < 0:  # evaluación de hoy: empezó hace un par de horas
        inicio = local - timedelta(hours=2, minutes=30)
    else:
        dia = (local - timedelta(days=plan.dias_atras)).date()
        inicio = datetime(dia.year, dia.month, dia.day, plan.hora_local, 0, tzinfo=ART)
    return inicio.astimezone(timezone.utc).replace(tzinfo=None)


def crear_engine(db_url: str):
    """Engine para el acceso directo (fechas, verificación). Acepta las URL de los servicios
    gestionados (`postgres://…?sslmode=require`) vía `normalize_database_url`."""
    from sqlalchemy import create_engine

    from app.config import normalize_database_url
    url = normalize_database_url(db_url)
    if url.startswith("postgresql"):
        # executemany con psycopg2.extras.execute_batch: los UPDATE por sesión viajan en
        # páginas de 500 sentencias (2-3 idas y vueltas en vez de una por fila: importa cuando
        # la base está en otro continente).
        return create_engine(url, pool_pre_ping=True, executemany_mode="values_plus_batch",
                             executemany_batch_page_size=500, connect_args={"connect_timeout": 20})
    return create_engine(url)


def url_sin_clave(db_url: str) -> str:
    from sqlalchemy.engine import make_url

    from app.config import normalize_database_url
    try:
        return make_url(normalize_database_url(db_url)).render_as_string(hide_password=True)
    except Exception:  # noqa: BLE001
        return "(URL no válida)"


def verificar_base(engine, email: str) -> None:
    """Antes de cargar nada: la base responde y es la de la API (tiene al docente)."""
    from sqlalchemy import select
    from sqlalchemy.exc import OperationalError, ProgrammingError

    from app import models
    try:
        with engine.connect() as conn:
            fila = conn.execute(select(models.User.id).where(models.User.email == email)).first()
    except OperationalError as exc:
        raise SystemExit("No se pudo conectar a la base de --database-url. Usá la URL EXTERNA (la interna solo "
                         "funciona dentro del proveedor) y revisá usuario y clave. Detalle: "
                         + str(exc.orig).strip().splitlines()[0]) from None
    except ProgrammingError:
        raise SystemExit("La base de --database-url no tiene las tablas de ImprontIA: no es la base de la API.") from None
    if fila is None:
            raise SystemExit(f"La base indicada en --database-url no tiene al docente {email}: no parece ser la "
                             "misma base que usa la API. Revisá que sea la URL EXTERNA de la base del servicio.")


def tamanio_base(engine) -> Optional[dict]:
    from sqlalchemy import text
    if engine.dialect.name != "postgresql":
        db_path = engine.url.database
        return {"base_bytes": os.path.getsize(db_path)} if db_path and os.path.exists(db_path) else None
    with engine.connect() as conn:
        return {
            "base_bytes": conn.execute(text("SELECT pg_database_size(current_database())")).scalar(),
            "eventos_bytes": conn.execute(text("SELECT pg_total_relation_size('events')")).scalar(),
        }


def liberar_espacio(db_url: str) -> None:
    """
    Después de borrar una demo anterior (PostgreSQL): VACUUM marca como reutilizable el lugar
    de las filas borradas, así la carga nueva lo ocupa en vez de agrandar la base (sin esto,
    hasta que pase el autovacuum, cada recarga sumaba otros ~40 MB). No bloquea la tabla ni
    toca datos; si el usuario de la base no tiene permiso, se sigue sin él.
    """
    engine = crear_engine(db_url)
    try:
        if engine.dialect.name != "postgresql":
            return
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            for tabla in ("events", "metrics", "indicator_metrics", "indicators", "sessions"):
                conn.exec_driver_sql(f"VACUUM {tabla}")
    except Exception as exc:  # noqa: BLE001 — optimización, no imprescindible
        print(f"  (no se pudo ejecutar VACUUM: {type(exc).__name__}; el espacio se libera con el autovacuum)")
    finally:
        engine.dispose()


def fechar(db_url: str, ancla: datetime, cargadas: list) -> None:
    """
    Corre las fechas de cada evaluación a su día (la API siempre usa "ahora"). Toca solo las
    filas de las evaluaciones recién cargadas (por id). UPDATE masivos: una sentencia por
    sesión y por tabla, enviadas en tandas; con PostgreSQL remoto son pocas idas y vueltas.

    Los eventos crudos NO se tocan: su `server_received_at` queda con la hora real de la carga.
    No lo muestra la API ni lo usa ningún cálculo (la duración, el panorama y la retención
    salen de la sesión), y en PostgreSQL un UPDATE de todas las filas de `events` deja una
    versión vieja de cada una: medido, duplicaba la tabla (37 -> 72 MB en la escala liviana,
    ~140 -> 266 MB en la completa) hasta un VACUUM FULL.
    """
    from sqlalchemy import bindparam, select, update

    from app import models

    engine = crear_engine(db_url)
    ses_t = models.Session.__table__
    met_t, ind_t = models.Metric.__table__, models.Indicator.__table__
    ex_t, pol_t, rev_t = models.Exam.__table__, models.PolicyCapture.__table__, models.Review.__table__
    try:
        with engine.begin() as conn:
            ids_exam = [d["exam"]["id"] for _, d, _ in cargadas]
            encontrados = {r[0]: r[1] for r in conn.execute(
                select(ex_t.c.id, ex_t.c.cerrada_at).where(ex_t.c.id.in_(ids_exam)))}
            faltan = [i for i in ids_exam if i not in encontrados]
            if faltan:
                raise SystemExit(f"Las evaluaciones recién cargadas no están en la base de --database-url "
                                 f"({len(faltan)} de {len(ids_exam)}): esa base no es la de la API. "
                                 "Las fechas quedaron sin ajustar (todo con fecha de hoy).")
            politicas = {}
            for pid, eid, creada in conn.execute(select(pol_t.c.id, pol_t.c.exam_id, pol_t.c.created_at)
                                                 .where(pol_t.c.exam_id.in_(ids_exam))):
                politicas.setdefault(eid, []).append((creada, pid))

            filas_exam, filas_pol, filas_ses, filas_rev, filas_modelo = [], [], [], [], []
            for plan, datos, reviews in cargadas:
                rng = np.random.default_rng(plan.semilla + 2000)
                inicio = _inicio_utc(ancla, plan)
                exam_id = datos["exam"]["id"]
                # Creada unos días antes, a media tarde (hora argentina).
                dia_creacion = (inicio.replace(tzinfo=timezone.utc).astimezone(ART)
                                - timedelta(days=1 if plan.abierta else 6)).date()
                creada = (datetime(dia_creacion.year, dia_creacion.month, dia_creacion.day, 15, tzinfo=ART)
                          + timedelta(minutes=float(rng.uniform(0, 150))))
                creada = creada.astimezone(timezone.utc).replace(tzinfo=None)
                for k, (_, pid) in enumerate(sorted(politicas.get(exam_id, []))):
                    filas_pol.append({"b_id": pid, "b_t": creada + timedelta(days=2 * k, minutes=5 * k)})

                ultimo_fin = inicio
                for s_info in datos["sesiones"]:
                    llegada = float(rng.uniform(0, 6 * 60_000))          # entran escalonados
                    lectura = float(rng.uniform(150_000, 480_000))        # leen la consigna antes de escribir
                    started = inicio + timedelta(milliseconds=llegada)
                    ended = started + timedelta(milliseconds=lectura + s_info["span_ms"] + 4_000)
                    filas_ses.append({"b_id": s_info["id"], "b_ini": started, "b_fin": ended,
                                      "b_proc": ended + timedelta(seconds=1)})
                    ultimo_fin = max(ultimo_fin, ended)

                cierre = None
                if encontrados[exam_id] is not None:
                    cierre = ultimo_fin + timedelta(minutes=float(rng.uniform(15, 40)))
                    filas_modelo += [{"b_id": s["id"], "b_t": cierre + timedelta(seconds=2)} for s in datos["sesiones"]]
                    for review_id, horas in reviews:
                        filas_rev.append({"b_id": review_id, "b_t": cierre + timedelta(hours=horas)})
                filas_exam.append({"b_id": exam_id, "b_creada": creada, "b_cierre": cierre})

            # Evaluaciones: creación siempre; cierre solo si está cerrada.
            conn.execute(update(ex_t).where(ex_t.c.id == bindparam("b_id"))
                         .values(created_at=bindparam("b_creada")), filas_exam)
            cerradas = [f for f in filas_exam if f["b_cierre"] is not None]
            if cerradas:
                conn.execute(update(ex_t).where(ex_t.c.id == bindparam("b_id"))
                             .values(cerrada_at=bindparam("b_cierre")), cerradas)
            if filas_pol:
                conn.execute(update(pol_t).where(pol_t.c.id == bindparam("b_id"))
                             .values(created_at=bindparam("b_t")), filas_pol)
            conn.execute(update(ses_t).where(ses_t.c.id == bindparam("b_id"))
                         .values(started_at=bindparam("b_ini"), ended_at=bindparam("b_fin"),
                                 procesada_at=bindparam("b_proc")), filas_ses)
            conn.execute(update(met_t).where(met_t.c.session_id == bindparam("b_id"))
                         .values(computed_at=bindparam("b_proc")), filas_ses)
            conn.execute(update(ind_t).where(ind_t.c.session_id == bindparam("b_id"),
                                             ind_t.c.kind != "atipico_modelo_poblacional")
                         .values(computed_at=bindparam("b_proc")), filas_ses)
            if filas_modelo:
                conn.execute(update(ind_t).where(ind_t.c.session_id == bindparam("b_id"),
                                                 ind_t.c.kind == "atipico_modelo_poblacional")
                             .values(computed_at=bindparam("b_t")), filas_modelo)
            if filas_rev:
                conn.execute(update(rev_t).where(rev_t.c.id == bindparam("b_id"))
                             .values(created_at=bindparam("b_t")), filas_rev)
    finally:
        engine.dispose()


# --------------------------------------------------------------------------------------
# Evaluaciones de la demo existentes, borrado
# --------------------------------------------------------------------------------------

ROTULO_DEMO = " [DEMO]"
NOMBRES_DEMO = {p.nombre for p in PLAN}


def es_demo(nombre: str) -> bool:
    return nombre in NOMBRES_DEMO or nombre.removesuffix(ROTULO_DEMO) in NOMBRES_DEMO


def contar_origen(api, auth: dict, exam_id: str) -> tuple:
    """(sesiones sintéticas de la demo, otras sesiones) de una evaluación, según `context.origen`."""
    sesiones = api.get("/sessions", what="listar sesiones", params={"exam_id": exam_id}, headers=auth).json()
    sinteticas = 0
    for s in sesiones:
        det = api.get(f"/sessions/{s['id']}", what="detalle de sesión", headers=auth).json()
        sinteticas += int((det.get("context") or {}).get("origen") == "demo_sintetica")
    return sinteticas, len(sesiones) - sinteticas


def clasificar(api, auth: dict, existentes: list) -> tuple:
    """
    Separa las evaluaciones del docente en (demo, otras). Revisión independiente del 30/10: el nombre
    solo no alcanza (una evaluación real podría llamarse igual). Una evaluación cuenta como demo si su
    nombre es de la demo Y tiene sesiones sintéticas que son mayoría. Así se
    admiten las pocas sesiones rendidas en vivo durante una presentación, y una evaluación real con
    el mismo nombre (sin sesiones sintéticas) nunca se borra.
    """
    demo, otras, en_vivo = [], [], 0
    for e in existentes:
        if not es_demo(e["name"]):
            otras.append(e)
            continue
        sint, resto = contar_origen(api, auth, e["id"])
        if sint > 0 and sint >= resto:
            demo.append(e)
            en_vivo += resto
        else:
            otras.append(e)
    return demo, otras, en_vivo


def confirmar_borrado(email: str, confirmacion: Optional[str], destino_remoto: bool, cuantas: int) -> None:
    """En la plataforma desplegada (o una base que no es el SQLite local) borrar exige confirmación."""
    if not destino_remoto:
        return
    if confirmacion is not None:
        if confirmacion.strip().lower() != email.lower():
            raise SystemExit(f"--si-borrar tiene que ser exactamente el email del docente ({email}). No se borró nada.")
        return
    if sys.stdin.isatty():
        print(f"Se van a ELIMINAR {cuantas} evaluaciones de demostración de {email} (con sus sesiones y "
              "revisiones) en la plataforma desplegada. No se puede deshacer.")
        if input(f"Para confirmar, escribí el email del docente: ").strip().lower() == email.lower():
            return
        raise SystemExit("El email no coincide. No se borró nada.")
    raise SystemExit(f"Para borrar en la plataforma desplegada agregá --si-borrar {email}. No se borró nada.")


# --------------------------------------------------------------------------------------

def _mb(n: Optional[int]) -> str:
    return "?" if n is None else f"{n / 1024 / 1024:.1f} MB"


def main(argv=None) -> int:
    import time

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--email", default=DEFAULT_EMAIL)
    ap.add_argument("--clave", default=None,
                    help=f"clave del docente (local: {DEFAULT_PASSWORD}; con --api: la de SEED_TEACHERS; "
                         "si no se indica se toma de IMPRONTIA_CLAVE_DEMO o se pide por teclado)")
    ap.add_argument("--database-url", default=None,
                    help="base a poblar (local) o a fechar (con --api). Acepta postgres://…?sslmode=require. "
                         "Default sin --api: DATABASE_URL o sqlite:///./impronta.db")
    ap.add_argument("--api", default=None,
                    help="URL de un backend ya levantado. Sin esto, la API se ejecuta dentro del script.")
    ap.add_argument("--escala", choices=["auto", "liviana", "completa"], default="auto",
                    help="eventos por sesión: completa (~5.000-8.000) o liviana (~1.000-1.700, 1 de cada "
                         f"{ESCALAS['liviana']} pulsaciones). auto = liviana contra la nube o PostgreSQL, "
                         "completa en el SQLite local")
    ap.add_argument("--lote", type=int, default=2500, help="eventos por pedido (máximo del servidor: 5000)")
    ap.add_argument("--paralelo", type=int, default=None,
                    help="sesiones enviadas en simultáneo (default: 4 con --api, 1 en modo local)")
    ap.add_argument("--ancla", default=None,
                    help="'ahora' de la demo, ISO 8601 (default: el momento en que se corre)")
    ap.add_argument("--reiniciar", action="store_true",
                    help="elimina antes las evaluaciones de demostración del docente (solo esas)")
    ap.add_argument("--solo-borrar", action="store_true",
                    help="elimina las evaluaciones de demostración del docente y termina (sin cargar nada)")
    ap.add_argument("--si-borrar", metavar="EMAIL", default=None,
                    help="confirmación para borrar en la plataforma desplegada: el email del docente")
    ap.add_argument("--conservar-otras", action="store_true",
                    help="cargar aunque el docente tenga evaluaciones que no son de la demo (no se tocan)")
    ap.add_argument("--rotular", action="store_true",
                    help=f"agrega '{ROTULO_DEMO.strip()}' al nombre de cada evaluación")
    ap.add_argument("--sin-fechas", action="store_true",
                    help="no tocar la base para fechar (todo queda con la fecha de hoy)")
    args = ap.parse_args(argv)

    from app.config import normalize_database_url

    t_inicio = time.monotonic()
    if args.api:
        # Con --api la base solo se usa para fechar, y solo si se indica (o hay DATABASE_URL).
        db_url = normalize_database_url(args.database_url or os.environ.get("DATABASE_URL")) \
            if (args.database_url or os.environ.get("DATABASE_URL")) else None
    else:
        if args.database_url:
            os.environ["DATABASE_URL"] = args.database_url
        db_url = normalize_database_url(os.environ.get("DATABASE_URL"))
    sqlite_local = db_url is not None and db_url.startswith("sqlite") and not args.api
    destino_remoto = not sqlite_local

    if not 1 <= args.lote <= 5000:
        raise SystemExit("--lote tiene que estar entre 1 y 5000 (límite del servidor por lote).")
    escala = args.escala if args.escala != "auto" else ("completa" if sqlite_local else "liviana")
    cada = ESCALAS[escala]
    paralelo = args.paralelo or (4 if args.api else 1)

    clave = args.clave
    if clave is None:
        if sqlite_local:
            clave = DEFAULT_PASSWORD
        else:
            clave = os.environ.get("IMPRONTIA_CLAVE_DEMO")
            if not clave and sys.stdin.isatty():
                import getpass
                clave = getpass.getpass(f"Clave de {args.email} en la plataforma: ")
            if not clave:
                raise SystemExit("Falta la clave del docente: --clave '...' (la misma de SEED_TEACHERS) "
                                 "o la variable IMPRONTIA_CLAVE_DEMO.")

    ancla = datetime.fromisoformat(args.ancla) if args.ancla else datetime.now(timezone.utc)
    if ancla.tzinfo is None:
        ancla = ancla.replace(tzinfo=ART)

    if args.api:
        import httpx
        base = args.api.rstrip("/")
        print(f"API: {base}")
        client = httpx.Client(base_url=base, timeout=httpx.Timeout(120.0, connect=20.0),
                              limits=httpx.Limits(max_connections=max(4, paralelo + 2)))
        info = esperar_api(client)
        print(f"  responde (versión {info.get('version', '?')}).")
    else:
        from fastapi.testclient import TestClient

        from app.main import app  # aplica las migraciones sobre la base elegida
        _asegurar_docente(args.email, clave, sqlite_local, clave_explicita=args.clave is not None)
        client = TestClient(app)
    api = Api(client)

    if db_url and not args.sin_fechas:
        print(f"Base: {url_sin_clave(db_url)}")
        if args.api:
            eng = crear_engine(db_url)
            try:
                verificar_base(eng, args.email)
            finally:
                eng.dispose()
    print(f"Escala: {escala} · lotes de hasta {args.lote} eventos · {paralelo} en simultáneo")

    r = client.post("/auth/login", json={"email": args.email, "password": clave})
    if r.status_code == 401:
        if args.api:
            raise SystemExit(
                f"No se pudo ingresar como {args.email}: email o clave incorrectos. En la plataforma desplegada "
                "este script NO crea el docente: tiene que existir (variable SEED_TEACHERS del servicio de la API, "
                "con el formato email:clave) y --clave tiene que ser esa misma clave. Probá primero ingresar al "
                "dashboard con esos datos.")
        raise SystemExit(f"No se pudo ingresar como {args.email}: clave incorrecta.")
    auth = {"Authorization": f"Bearer {_check(r, 'login').json()['access_token']}"}

    existentes = api.get("/exams", what="listar evaluaciones", headers=auth).json()
    demo, otras, en_vivo = clasificar(api, auth, existentes)

    if otras and not args.conservar_otras and not args.solo_borrar:
        # Se verifica ANTES de borrar nada: si no se va a cargar, tampoco se borra la demo anterior.
        print(f"El docente {args.email} tiene {len(otras)} evaluaciones que NO son de la demo ("
              + ", ".join(e["name"] for e in otras) + "). Para no mezclarlas con datos sintéticos conviene usar "
              "una cuenta solo para la demo; si igual querés cargarla (sin tocarlas), agregá --conservar-otras.")
        return 1
    if demo and not (args.reiniciar or args.solo_borrar):
        print(f"El docente {args.email} ya tiene {len(demo)} evaluaciones de la demo. Corré con --reiniciar "
              "para borrarlas y cargarla desde cero.")
        return 1

    if demo:
        confirmar_borrado(args.email, args.si_borrar, destino_remoto, len(demo))
        for e in demo:
            api.delete(f"/exams/{e['id']}", what="eliminar evaluación", headers=auth)
        print(f"Eliminadas {len(demo)} evaluaciones de demostración de {args.email}"
              + (f" (incluían {en_vivo} sesiones rendidas en vivo, no sintéticas)." if en_vivo else "."))
        if otras:
            print(f"No se tocaron sus otras {len(otras)} evaluaciones: " + ", ".join(e["name"] for e in otras))
        if db_url and not args.sin_fechas:
            liberar_espacio(db_url)
    elif args.solo_borrar:
        print(f"{args.email} no tiene evaluaciones de demostración.")
    if args.solo_borrar:
        return 0

    cargadas = []
    for plan in PLAN:
        t0 = time.monotonic()
        nombre = plan.nombre + (ROTULO_DEMO if args.rotular else "")
        datos = cargar_evaluacion(api, auth, plan, cada=cada, lote=args.lote, paralelo=paralelo,
                                  nombre=nombre, escala=escala)
        reviews = revisar(api, auth, plan, datos["exam"]["id"])
        cargadas.append((plan, datos, reviews))
        estado = "abierta" if plan.abierta else "cerrada"
        eventos = sum(s["eventos"] for s in datos["sesiones"])
        print(f"  {nombre}: {len(datos['sesiones'])} sesiones ({eventos:,} eventos), {estado}, "
              f"{len(reviews)} revisiones · código {datos['exam']['join_code']} · {time.monotonic() - t0:.0f} s",
              flush=True)

    if args.sin_fechas:
        print("Fechas sin ajustar (--sin-fechas): todo quedó con la fecha y hora de hoy.")
    elif db_url is None:
        print("\nATENCIÓN: sin acceso a la base (--database-url) las fechas NO se ajustaron: las seis evaluaciones "
              "quedan con la fecha de hoy y la duración de cada sesión (inicio a entrega) es la de la carga, de "
              "unos segundos. Para que cada evaluación quede en su día, volvé a correr con --reiniciar y "
              "--database-url con la URL externa de la base.")
    else:
        t0 = time.monotonic()
        fechar(db_url, ancla, cargadas)
        print(f"Fechas ajustadas: cada evaluación quedó en su día ({time.monotonic() - t0:.1f} s).")
        eng = crear_engine(db_url)
        try:
            tam = tamanio_base(eng)
        finally:
            eng.dispose()
        if tam:
            extra = f" (eventos: {_mb(tam['eventos_bytes'])})" if "eventos_bytes" in tam else ""
            print(f"Tamaño de la base: {_mb(tam['base_bytes'])}{extra}.")

    recu = cargadas[-1][1]["exam"]
    print(f"\nListo en {time.monotonic() - t_inicio:.0f} s ({api.pedidos} pedidos, {api.reintentados} reintentos). "
          f"Ingresá con {args.email}" + (f" / {clave}." if sqlite_local else " y su clave."))
    print(f"Para rendir en vivo el recuperatorio (queda abierto con {len(cargadas[-1][1]['sesiones'])} entregas): "
          f"código {recu['join_code']}  ->  /exam/{recu['join_code']}")
    print("Recordá: son datos SINTÉTICOS de demostración (participantes y respuestas inventados).")
    return 0


def _asegurar_docente(email: str, clave: str, sqlite_local: bool, clave_explicita: bool) -> None:
    """
    Modo local (la API corre dentro del script). En el SQLite de desarrollo se crea el docente
    o se resetea su clave, como siempre. Contra cualquier otra base (p. ej. PostgreSQL de
    producción) NUNCA se cambia la clave de un docente existente, y para crearlo se exige una
    clave explícita (no la de desarrollo).
    """
    if sqlite_local:
        from scripts.seed_teacher import main as crear_docente
        crear_docente(email, clave)
        return
    from app.auth import hash_password
    from app.database import SessionLocal
    from app.models import User
    db = SessionLocal()
    try:
        if db.query(User).filter(User.email == email).first():
            return
        if not clave_explicita:
            raise SystemExit(f"El docente {email} no existe en esa base. Para crearlo indicá --clave (no se usa "
                             "la clave de desarrollo fuera del SQLite local).")
        db.add(User(email=email, password_hash=hash_password(clave)))
        db.commit()
        print(f"Docente creado: {email}")
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
