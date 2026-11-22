"""
Modelo de datos del MVP.

A partir del Incremento 5 (ver mvp/docs/bitacora.md) este archivo sigue de
cerca el modelo entidad-relación del cap. 15 ("Modelo de datos", 10
entidades: usuario, evaluacion, politica_captura, sesion, evento, metrica,
indicador, revision, + 2 tablas de unión N:M) en vez del diseño más simple
del Incremento 1. Trazabilidad de requisitos por entidad:

- Exam           -> identidad de la evaluación (nombre, join_code, consigna)
- PolicyCapture  -> RF01, RF02, RF04, RNF04 (snapshot versionado de qué se informa y qué se captura)
- Session        -> RF03, RF05 (una rendición, ancla un snapshot de política + contexto)
- Event          -> RF03, RNF04 (fila por evento, solo inserción, secuencia monotónica)
- Metric         -> procesamiento determinístico (cap. 15, "Procesamiento e IA")
- Indicator      -> RF06, RF07, RF09, RNF06 (detección + trazabilidad + explicabilidad)
- IndicatorMetric-> RNF05 (relación N:M real indicador<->métrica, no solo JSON descriptivo)
- Review         -> RF10, RF11 (única fuente de decisión académica)
- ReviewIndicator-> una revisión puede atender varios indicadores puntuales, o ninguno
"""
import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, Column, DateTime, Enum, Float, ForeignKey, Integer, String, Text,
    LargeBinary,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import deferred, relationship
from sqlalchemy.types import JSON as SQLITE_JSON

from .database import Base
from .processing.rules import rules_from_stored

# JSONB en Postgres, JSON plano en SQLite (desarrollo local sin Docker).
JSONType = JSONB().with_variant(SQLITE_JSON(), "sqlite")


def utcnow() -> datetime:
    """
    Instante actual en UTC, sin zona (naive), como se guarda en todas las columnas DateTime.

    Reemplaza a `datetime.utcnow()`, deprecado desde Python 3.12 (hallazgo B11 de la
    revisión del 13/10): el valor guardado es el mismo, así que la serialización con
    offset +00:00 de schemas.py y los datos ya existentes no cambian.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def gen_uuid() -> str:
    return str(uuid.uuid4())


def gen_join_code() -> str:
    return uuid.uuid4().hex[:6].upper()


class UserRole(str, enum.Enum):
    docente = "docente"


class User(Base):
    """Docente/Evaluador. El estudiante no tiene cuenta en el MVP (ver bitácora)."""

    __tablename__ = "users"

    id = Column(String, primary_key=True, default=gen_uuid)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    role = Column(Enum(UserRole), nullable=False, default=UserRole.docente)
    created_at = Column(DateTime, default=utcnow)

    exams = relationship("Exam", back_populates="teacher")


class Exam(Base):
    """
    Evaluación. Identidad estable de la instancia (nombre, join_code, consigna).

    Qué se informa y qué señales se habilitan NO vive acá — vive en
    PolicyCapture, versionado, para que un cambio posterior no reinterprete
    retroactivamente sesiones ya rendidas (RNF04, cap. 15 sección "Modelo de
    datos").
    """

    __tablename__ = "exams"

    id = Column(String, primary_key=True, default=gen_uuid)
    teacher_id = Column(String, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    join_code = Column(String, unique=True, nullable=False, default=gen_join_code)
    prompt_text = Column(Text, nullable=False, default="")  # consigna: la plataforma aloja la superficie de respuesta
    created_at = Column(DateTime, default=utcnow)
    # Incremento 16: cierre de la evaluación. Al cerrarla se ejecuta el análisis poblacional
    # (Isolation Forest) sobre TODAS las sesiones finalizadas con un único protocolo
    # (processing/cohort.py) y no se admiten sesiones nuevas. None = abierta.
    cerrada_at = Column(DateTime, nullable=True)
    # Ejercicios del examen (nov. 2026): lista de {"id": "1", "enunciado": "..."}. Con un PDF
    # adjunto, los enunciados pueden quedar vacíos: el PDF es el enunciado y cada ítem es solo un
    # campo de respuesta. None = evaluación anterior, de una sola consigna (prompt_text).
    items = Column(JSONType, nullable=True)

    teacher = relationship("User", back_populates="exams")
    documento = relationship("ExamDocument", uselist=False, back_populates="exam", lazy="select")

    @property
    def tiene_pdf(self) -> bool:
        return self.documento is not None

    @property
    def pdf_nombre(self):
        return self.documento.nombre if self.documento is not None else None
    sessions = relationship("Session", back_populates="exam")
    policies = relationship(
        "PolicyCapture", back_populates="exam", order_by="PolicyCapture.created_at"
    )

    @property
    def current_policy(self) -> "PolicyCapture | None":
        return self.policies[-1] if self.policies else None

    @property
    def policy_version(self) -> int:
        """Número de la versión vigente (1 = la creada con el examen). Ver PolicyCapture."""
        return len(self.policies)


class PolicyCapture(Base):
    """
    Snapshot versionado de qué se informa (RF01/RF02) y qué señales se
    habilitan (RF04) para una evaluación. Inmutable una vez creado: editar
    la política de un examen crea una fila NUEVA, nunca actualiza una
    existente — así una sesión que ya referencia una versión no queda
    reinterpretada por un cambio posterior (RNF04).
    """

    __tablename__ = "policy_captures"

    id = Column(String, primary_key=True, default=gen_uuid)
    exam_id = Column(String, ForeignKey("exams.id"), nullable=False)
    info_text = Column(Text, nullable=False, default="")  # RF01
    rules_text = Column(Text, nullable=False, default="")  # RF02
    allowed_signals = Column(JSONType, nullable=False, default=list)  # RF04
    created_at = Column(DateTime, default=utcnow)
    # Fase 2 (P02, migración 0002): plazo de conservación de eventos y métricas (RNF10,
    # cap. 15). None = sin plazo definido (todas las políticas anteriores). Máximo
    # RETENCION_MAX_DIAS. Solo se guarda: la purga periódica es una tarea aparte.
    retencion_dias = Column(Integer, nullable=True)

    exam = relationship("Exam", back_populates="policies")
    sessions = relationship("Session", back_populates="policy")

    # Incremento 12 (R2): reglas del examen guardadas como entradas reservadas dentro del
    # mismo JSON `allowed_signals` (sin cambio de esquema). Ver processing/rules.py.
    @property
    def permite_pegado(self) -> bool:
        return rules_from_stored(self.allowed_signals)["permite_pegado"]

    @property
    def permite_otras_pestanas(self) -> bool:
        return rules_from_stored(self.allowed_signals)["permite_otras_pestanas"]


class SessionStatus(str, enum.Enum):
    active = "active"
    ended = "ended"


class ExamDocument(Base):
    """Enunciado del examen en PDF (nov. 2026). Tabla aparte para no cargar el binario con el examen."""

    __tablename__ = "exam_documents"

    exam_id = Column(String, ForeignKey("exams.id"), primary_key=True)
    nombre = Column(String, nullable=False)
    contenido = deferred(Column(LargeBinary, nullable=False))  # se lee solo al descargarlo
    created_at = Column(DateTime, default=utcnow)

    exam = relationship("Exam", back_populates="documento")


class Session(Base):
    """Una rendición de un estudiante, anclada a un examen y a un snapshot de política."""

    __tablename__ = "sessions"

    id = Column(String, primary_key=True, default=gen_uuid)
    exam_id = Column(String, ForeignKey("exams.id"), nullable=False)
    policy_id = Column(String, ForeignKey("policy_captures.id"), nullable=False)
    participant_id = Column(String, nullable=False)  # identificador pseudónimo
    session_type = Column(String, nullable=False, default="exam")  # calibration|exam|practice
    status = Column(Enum(SessionStatus), nullable=False, default=SessionStatus.active)
    context = Column(JSONType, nullable=False, default=dict)  # RF05: curso, actividad, etc.
    session_token = Column(String, unique=True, nullable=False, default=gen_uuid)
    consent_given = Column(Boolean, nullable=False, default=False)
    needs_review = Column(Boolean, nullable=False, default=False)  # RF06/RF07, derivado
    next_event_seq = Column(Integer, nullable=False, default=0)  # asigna Event.seq de forma monotónica
    last_batch_seq = Column(Integer, nullable=False, default=0)  # idempotencia de red: último EventBatchIn.seq aplicado
    started_at = Column(DateTime, default=utcnow)
    ended_at = Column(DateTime, nullable=True)
    # P03 (kit de simulación): condición simulada que declara quien rinde una sesión de
    # prueba ("normal", "pegado", ...). NULL en toda sesión real. El docente NO la ve
    # (no está en ningún esquema de salida) y el pipeline no la lee: solo la usan
    # scripts/exportar_sesiones.py y scripts/analizar_reales.py.
    condicion_simulacion = Column(String, nullable=True)
    # Respuestas por ejercicio (nov. 2026): {"1": "...", "2": "..."}. `respuesta` sigue guardando
    # el texto completo (todas las respuestas, rotuladas) para lo que ya lo usaba.
    respuestas = Column(JSONType, nullable=True)
    # Incremento 16.
    # - procesada_at: cuándo terminó el procesamiento (métricas + reglas). None con la sesión
    #   finalizada = el procesamiento falló o no corrió; se reintenta al repetir el cierre.
    # - estado_modelo: resultado del análisis poblacional para ESTA sesión:
    #   "pendiente" (la evaluación sigue abierta), "no_evaluada" (población insuficiente o
    #   sesión finalizada después del cierre), "sin_marca" o "con_marca".
    # - respuesta: la respuesta entregada por el estudiante (la entrega del examen). No es una
    #   señal: el procesamiento no la lee y solo la ve el docente de la evaluación.
    procesada_at = Column(DateTime, nullable=True)
    estado_modelo = Column(String, nullable=False, default="pendiente", server_default="pendiente")
    respuesta = Column(Text, nullable=True)

    exam = relationship("Exam", back_populates="sessions")
    policy = relationship("PolicyCapture", back_populates="sessions")
    events = relationship("Event", back_populates="session", order_by="Event.seq")
    metrics = relationship("Metric", back_populates="session")
    indicators = relationship("Indicator", back_populates="session")
    reviews = relationship("Review", back_populates="session")


class Event(Base):
    """
    Registro crudo de una interacción individual. Solo inserción — nunca se
    actualiza ni se borra una fila existente (RNF04). Reemplaza el diseño
    anterior de lotes-como-JSON-blob (ver bitácora, Incremento 5): ahora hay
    una fila por evento, indexada por (session_id, seq), tal como describe
    cap. 15 sección "Modelo de datos".
    """

    __tablename__ = "events"

    id = Column(String, primary_key=True, default=gen_uuid)
    session_id = Column(String, ForeignKey("sessions.id"), nullable=False, index=True)
    seq = Column(Integer, nullable=False)  # monotónico por sesión, asignado por el servidor
    client_t = Column(Float, nullable=False)  # ms relativos al inicio de sesión, según el cliente
    server_received_at = Column(DateTime, default=utcnow)
    type = Column(String, nullable=False)
    item_ref = Column(String, nullable=True)  # pregunta/ítem al que corresponde, si está disponible
    payload = Column(JSONType, nullable=False, default=dict)  # resto de los campos del evento (nunca contenido)

    session = relationship("Session", back_populates="events")


class Metric(Base):
    """Métrica derivada del procesamiento determinístico sobre los eventos de una sesión."""

    __tablename__ = "metrics"

    id = Column(String, primary_key=True, default=gen_uuid)
    session_id = Column(String, ForeignKey("sessions.id"), nullable=False)
    name = Column(String, nullable=False)  # ej. "mean_dwell_time_ms"
    value = Column(Float, nullable=False)
    item_ref = Column(String, nullable=True)  # denormalizado desde los eventos de origen; None = agregado de sesión completa
    computed_at = Column(DateTime, default=utcnow)
    # Fase 2 (P02): rango de Event.seq sobre el que se calculó (cap. 15: evento_desde/
    # evento_hasta, RNF05). None si la sesión no tenía eventos o si la métrica es anterior
    # a la migración 0002.
    evento_desde = Column(Integer, nullable=True)
    evento_hasta = Column(Integer, nullable=True)

    session = relationship("Session", back_populates="metrics")


ESTADOS_MODELO = ("pendiente", "no_evaluada", "sin_marca", "con_marca")
RETENCION_MAX_DIAS = 365  # tope de PolicyCapture.retencion_dias (revisión del 16/10, D11)
INDICATOR_ESTADOS = ("pendiente", "atendido")


class IndicatorLevel(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"


class Indicator(Base):
    """
    Indicador preliminar para priorizar revisión docente.

    No representa una conclusión sobre fraude (RF10): solo señala que ciertas
    métricas superaron un umbral (o resultaron atípicas frente a la línea
    base poblacional), y guarda la explicación para trazabilidad (RF09,
    RNF05/06). Sin columna de veredicto, tal como exige cap. 15.
    """

    __tablename__ = "indicators"

    id = Column(String, primary_key=True, default=gen_uuid)
    session_id = Column(String, ForeignKey("sessions.id"), nullable=False)
    kind = Column(String, nullable=False)  # ej. "paste_volume_alto", "atipico_modelo_poblacional"
    level = Column(Enum(IndicatorLevel), nullable=False, default=IndicatorLevel.medium)
    description = Column(Text, nullable=False)
    explanation = Column(JSONType, nullable=False, default=dict)  # snapshot legible; la relación real está en IndicatorMetric
    computed_at = Column(DateTime, default=utcnow)
    # Fase 2 (P02): "pendiente" | "atendido" (cap. 15: indicador.estado). Pasa a "atendido"
    # cuando una revisión docente lo cita. No es un veredicto: la decisión vive en Review.
    estado = Column(String, nullable=False, default="pendiente", server_default="pendiente")

    session = relationship("Session", back_populates="indicators")
    indicator_metrics = relationship("IndicatorMetric", back_populates="indicator")
    review_links = relationship("ReviewIndicator", back_populates="indicator")


class IndicatorMetric(Base):
    """
    Relación N:M real indicador<->métrica (RNF05): un indicador puede
    sustentarse en varias métricas a la vez, permitiendo reconstruir el
    origen exacto sin depender únicamente del JSON `explanation`.
    """

    __tablename__ = "indicator_metrics"

    id = Column(String, primary_key=True, default=gen_uuid)
    indicator_id = Column(String, ForeignKey("indicators.id"), nullable=False)
    metric_id = Column(String, ForeignKey("metrics.id"), nullable=False)

    indicator = relationship("Indicator", back_populates="indicator_metrics")
    metric = relationship("Metric")


class ReviewAction(str, enum.Enum):
    marked_reviewed = "marked_reviewed"
    additional_validation = "additional_validation"  # RF11


class Review(Base):
    """Acción de revisión humana sobre una sesión. Nunca generada por el sistema (RF10). Solo inserción."""

    __tablename__ = "reviews"

    id = Column(String, primary_key=True, default=gen_uuid)
    session_id = Column(String, ForeignKey("sessions.id"), nullable=False)
    teacher_id = Column(String, ForeignKey("users.id"), nullable=False)
    action = Column(Enum(ReviewAction), nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow)

    session = relationship("Session", back_populates="reviews")
    teacher = relationship("User")
    indicator_links = relationship("ReviewIndicator", back_populates="review")


class ReviewIndicator(Base):
    """
    Relación N:M revisión<->indicador: una revisión puede atender varios
    indicadores puntuales de una sesión en un solo acto docente, o ninguno
    (una revisión "sin observaciones" no requiere indicador asociado).
    """

    __tablename__ = "review_indicators"

    id = Column(String, primary_key=True, default=gen_uuid)
    review_id = Column(String, ForeignKey("reviews.id"), nullable=False)
    indicator_id = Column(String, ForeignKey("indicators.id"), nullable=False)

    review = relationship("Review", back_populates="indicator_links")
    indicator = relationship("Indicator", back_populates="review_links")
