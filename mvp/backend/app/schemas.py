from datetime import datetime, timezone
from typing import Annotated, Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, PlainSerializer, field_validator

from .processing.rules import capture_signals

# Fase 2 (P02): plazo de conservación opcional de la política (RNF10). 1..365 días;
# None = sin plazo definido (comportamiento anterior).
RetencionDias = Optional[Annotated[int, Field(ge=1, le=365)]]

# Fase 2 (P03): condiciones del kit de simulación (docs/simulaciones/protocolo.md).
# Mismo orden que app/simulacion.py::CONDICIONES (un test verifica que coincidan).
CondicionSimulacion = Literal["normal", "pegado", "transcripcion", "consulta_externa", "suplantacion"]


def _as_utc_iso(dt: datetime) -> str:
    """
    Los modelos guardan `models.utcnow()` (naive, en UTC). Sin zona explícita,
    el navegador interpreta el ISO como hora LOCAL y el dashboard mostraba las
    horas corridas (-3 h en Argentina). Se serializa siempre con offset +00:00.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


# datetime que la API devuelve siempre como ISO 8601 con zona UTC explícita.
datetime_utc = Annotated[datetime, PlainSerializer(_as_utc_iso, return_type=str)]


# ---- Auth ----

class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AccountDeleteRequest(BaseModel):
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ---- Exams / Policy ----

MAX_ITEMS = 30


class ExamItem(BaseModel):
    """Un ejercicio del examen (nov. 2026). Con PDF adjunto el enunciado puede quedar vacío."""
    id: str = Field(min_length=1, max_length=16)
    enunciado: str = Field(default="", max_length=20_000)


class ExamCreate(BaseModel):
    name: str
    prompt_text: str
    # Ejercicios (nov. 2026). None = una sola consigna en prompt_text (comportamiento anterior).
    items: Optional[list[ExamItem]] = Field(default=None, max_length=MAX_ITEMS)
    info_text: str
    rules_text: str
    allowed_signals: list[str]
    # Incremento 12 (R2): reglas que vuelven "permitidos" algunos indicadores. Default
    # False = comportamiento anterior.
    permite_pegado: bool = False
    permite_otras_pestanas: bool = False
    retencion_dias: RetencionDias = None


class PolicyOut(BaseModel):
    id: str
    info_text: str
    rules_text: str
    allowed_signals: list[str]  # solo señales de captura (sin las entradas reservadas de reglas)
    permite_pegado: bool = False
    permite_otras_pestanas: bool = False
    retencion_dias: Optional[int] = None
    created_at: datetime_utc

    @field_validator("allowed_signals", mode="before")
    @classmethod
    def _solo_senales(cls, v):
        return capture_signals(v)

    model_config = ConfigDict(from_attributes=True)


class ExamOut(BaseModel):
    id: str
    name: str
    join_code: str
    prompt_text: str
    created_at: datetime_utc
    cerrada_at: Optional[datetime_utc] = None  # Incremento 16
    items: Optional[list[ExamItem]] = None
    tiene_pdf: bool = False
    pdf_nombre: Optional[str] = None
    current_policy: PolicyOut
    policy_version: int  # 1 = política original; cada POST /exams/{id}/policy suma una versión (RNF04)

    model_config = ConfigDict(from_attributes=True)


class PolicyUpdate(BaseModel):
    """Crea una NUEVA versión de política (RNF04) — nunca edita la vigente."""
    info_text: str
    rules_text: str
    allowed_signals: list[str]
    permite_pegado: bool = False
    permite_otras_pestanas: bool = False
    retencion_dias: RetencionDias = None


class ExamPublicInfo(BaseModel):
    """Lo único que ve el estudiante antes de aceptar (RF01/RF02): sin datos internos del examen."""
    name: str
    info_text: str
    rules_text: str
    allowed_signals: list[str]
    # Incremento 16: el estudiante ve, antes del consentimiento, si la evaluación ya cerró
    # (POST /sessions/start respondería 409).
    cerrada: bool = False


# ---- Sessions ----

class SessionStartRequest(BaseModel):
    exam_code: str
    participant_id: str
    session_type: str = "exam"
    context: dict[str, Any] = {}
    consent_given: bool
    # P03: solo para simulaciones de examen. Opcional; el docente no la ve.
    condicion_simulacion: Optional[CondicionSimulacion] = None


class SessionStartResponse(BaseModel):
    session_id: str
    session_token: str
    allowed_signals: list[str]
    info_text: str
    rules_text: str
    prompt_text: str
    items: Optional[list[ExamItem]] = None
    tiene_pdf: bool = False


class EventBatchIn(BaseModel):
    seq: int  # seq de lote (idempotencia de red); Event.seq real lo asigna el servidor por evento
    events: list[dict[str, Any]]


class SessionEndRequest(BaseModel):
    # Incremento 16: respuesta entregada por el estudiante (la entrega del examen). No es una
    # señal de interacción: el procesamiento no la lee y solo la ve el docente.
    respuesta: Optional[str] = Field(default=None, max_length=100_000)
    # Nov. 2026: respuestas por ejercicio, {"1": "...", ...}.
    respuestas: Optional[dict[str, str]] = Field(default=None, max_length=MAX_ITEMS)


class IndicatorBrief(BaseModel):
    kind: str
    level: str
    prioriza: bool


class SessionSummary(BaseModel):
    id: str
    exam_id: str
    exam_name: str
    participant_id: str
    session_type: str
    status: str
    needs_review: bool
    started_at: datetime_utc
    ended_at: Optional[datetime_utc]
    # Estado de la revisión docente, DERIVADO de la última Review (las revisiones son solo
    # inserción, RF10/RNF04): "sin_revision" | "revisada" | "validacion_pendiente" (RF11/HU08).
    review_status: str
    last_review_at: Optional[datetime_utc]
    last_review_notes: Optional[str]
    # Incremento 16: "pendiente" | "no_evaluada" | "sin_marca" | "con_marca"
    estado_modelo: str = "pendiente"
    # Rediseño del panel (nov. 2026): tipos de indicador de la sesión, para que la lista muestre
    # de un vistazo POR QUÉ una sesión pide revisión. `prioriza` es False para los avisos
    # informativos y para lo permitido por las reglas del examen (no marcan la sesión).
    indicadores: list[IndicatorBrief] = []


class MetricOut(BaseModel):
    id: str
    name: str
    value: float
    item_ref: Optional[str]
    evento_desde: Optional[int] = None  # rango de Event.seq de origen (P02)
    evento_hasta: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class IndicatorOut(BaseModel):
    id: str
    kind: str
    level: str
    estado: str = "pendiente"  # "pendiente" | "atendido" (P02)
    description: str
    explanation: dict[str, Any]
    metric_ids: list[str]  # trazabilidad relacional real (IndicatorMetric), no solo `explanation`
    computed_at: datetime_utc


# ---- Reviews ----

class ReviewCreate(BaseModel):
    action: str  # "marked_reviewed" | "additional_validation"
    notes: Optional[str] = None
    indicator_ids: list[str] = []  # a qué indicadores puntuales atiende esta revisión (puede ser ninguno)


class ReviewOut(BaseModel):
    id: str
    action: str
    notes: Optional[str]
    indicator_ids: list[str]
    created_at: datetime_utc
    teacher_email: Optional[str] = None


class SessionDetail(SessionSummary):
    context: dict[str, Any]
    metrics: list[MetricOut]
    indicators: list[IndicatorOut]
    event_count: int
    reviews: list[ReviewOut]  # historial completo, más antigua primero
    procesada: bool = True
    respuesta: Optional[str] = None
    # Nov. 2026: ejercicios del examen y respuestas por ejercicio.
    items: Optional[list[ExamItem]] = None
    respuestas: Optional[dict[str, str]] = None
    tiene_pdf: bool = False


# ---- Panorama de la evaluación (Incremento 12, R1) ----

class PanoramaMetric(BaseModel):
    metric: str
    n: int
    mediana: Optional[float] = None
    p25: Optional[float] = None
    p75: Optional[float] = None


class PanoramaIndicator(BaseModel):
    kind: str
    sesiones: int
    permitidas_por_reglas: int
    porcentaje: float


class PanoramaModelFeature(BaseModel):
    metric: str
    sesiones: int


class PanoramaModel(BaseModel):
    sesiones_marcadas: int
    porcentaje: float
    metricas_frecuentes: list[PanoramaModelFeature]


class PanoramaCobertura(BaseModel):
    # Incremento 16: qué parte de la evaluación está analizada por el modelo poblacional.
    evaluacion_cerrada: bool
    sesiones_evaluadas: int
    sesiones_no_evaluadas: int
    sesiones_pendientes: int


class PanoramaOut(BaseModel):
    """Resumen agregado de las sesiones FINALIZADAS de una evaluación, calculado solo sobre
    Metric/Indicator ya guardados (sin recalcular ni cambiar el esquema)."""
    exam_id: str
    n_sesiones: int
    sesiones_requieren_revision: int
    metricas: list[PanoramaMetric]
    indicadores: list[PanoramaIndicator]
    modelo: PanoramaModel
    cobertura: Optional[PanoramaCobertura] = None
