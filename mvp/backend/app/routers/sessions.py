from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy.orm import Session as DBSession, contains_eager, selectinload, undefer

from .. import models, schemas
from ..auth import get_current_teacher
from ..database import get_db
from ..processing.event_schema import validate_batch
from ..processing.features import compute_all_features
from ..processing.indicators import INFORMATIVE_KINDS, IndicatorDraft
from ..processing.pipeline import evaluate_session
from ..processing.rules import capture_signals, rules_from_stored
from ..retention import delete_session_data

router = APIRouter(tags=["sessions"])

# 4 MB (nov. 2026, antes 10 MB): Vercel limita a 4,5 MB el cuerpo de cada pedido y de cada
# respuesta de una función; con 4 MB el PDF y el resto del formulario entran en ese límite.
MAX_PDF_BYTES = 4 * 1024 * 1024


def pdf_response(db: DBSession, exam_id: str) -> Response:
    doc = (
        db.query(models.ExamDocument)
        .options(undefer(models.ExamDocument.contenido))
        .filter(models.ExamDocument.exam_id == exam_id)
        .first()
    )
    if not doc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "La evaluación no tiene un enunciado en PDF")
    return Response(
        content=doc.contenido,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{doc.nombre}"', "Cache-Control": "private, no-store"},
    )


def respuesta_completa(exam: models.Exam, respuestas: dict[str, str]) -> str:
    """Texto completo de la entrega, rotulado por ejercicio, en el orden del examen."""
    orden = [str(i.get("id")) for i in (exam.items or [])]
    ids = orden + [k for k in respuestas if k not in orden]
    partes = [f"Ejercicio {k}:\n{respuestas[k].strip()}" for k in ids if respuestas.get(k, "").strip()]
    return "\n\n".join(partes)


def get_session_by_token(
    session_id: str,
    x_session_token: str = Header(...),
    db: DBSession = Depends(get_db),
) -> models.Session:
    """Autenticación del lado estudiante: token opaco emitido en /sessions/start."""
    session = db.query(models.Session).filter(models.Session.id == session_id).first()
    if not session or session.session_token != x_session_token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token de sesión inválido")
    return session


@router.post("/sessions/start", response_model=schemas.SessionStartResponse)
def start_session(payload: schemas.SessionStartRequest, db: DBSession = Depends(get_db)):
    exam = db.query(models.Exam).filter(models.Exam.join_code == payload.exam_code.upper()).first()
    if not exam or not exam.current_policy:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Evaluación no encontrada")
    if exam.cerrada_at is not None:
        # Incremento 16: el análisis poblacional se hizo al cerrar; una sesión nueva quedaría
        # fuera de la cohorte analizada.
        raise HTTPException(status.HTTP_409_CONFLICT, "La evaluación está cerrada")
    if not payload.consent_given:
        # RF01/RF02: el consentimiento se da sobre la info ya mostrada al estudiante.
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Se requiere consentimiento para iniciar la sesión")

    policy = exam.current_policy  # snapshot fijado ahora; cambios futuros a la política no lo afectan (RNF04)

    session = models.Session(
        exam_id=exam.id,
        policy_id=policy.id,
        participant_id=payload.participant_id,
        session_type=payload.session_type,
        context=payload.context,
        consent_given=True,
        condicion_simulacion=payload.condicion_simulacion,  # P03: oculta al docente
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    return schemas.SessionStartResponse(
        session_id=session.id,
        session_token=session.session_token,
        allowed_signals=capture_signals(policy.allowed_signals),  # RF04: el cliente debe limitar la captura a esto
        info_text=policy.info_text,
        rules_text=policy.rules_text,
        prompt_text=exam.prompt_text,  # recién se revela una vez iniciada la sesión (con consentimiento)
        items=exam.items,
        tiene_pdf=exam.tiene_pdf,
    )


@router.get("/sessions/{session_id}/enunciado.pdf")
def get_session_pdf(
    session: models.Session = Depends(get_session_by_token),
    db: DBSession = Depends(get_db),
):
    """Enunciado en PDF para el estudiante: solo con el token de una sesión ya iniciada (con consentimiento)."""
    return pdf_response(db, session.exam_id)


@router.post("/sessions/{session_id}/events", status_code=status.HTTP_201_CREATED)
def post_events(
    session_id: str,
    payload: schemas.EventBatchIn,
    session: models.Session = Depends(get_session_by_token),
    db: DBSession = Depends(get_db),
):
    # FastAPI cachea Depends(get_db) por request, por lo que `session` y `db`
    # comparten la misma Session de SQLAlchemy: no hace falta reatachar nada.
    if session.status != models.SessionStatus.active:
        raise HTTPException(status.HTTP_409_CONFLICT, "La sesión ya fue finalizada")

    # Incremento 16: la política se aplica también en el servidor (RF04, RNF01). Un lote con un
    # tipo, una categoría no habilitada, un campo o un valor no admitidos se rechaza completo.
    problems = validate_batch(payload.events, capture_signals(session.policy.allowed_signals))
    if problems:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, {"mensaje": "Lote rechazado", "problemas": problems[:10]})

    if payload.seq <= session.last_batch_seq:
        # Reintento de red de un lote ya aplicado (el cliente no recibió la confirmación
        # a tiempo y reintentó el mismo lote): idempotente, no se reinserta ni se cuenta
        # como error. Ver EventBatchIn.seq y mvp/docs/bitacora.md.
        return {"stored": 0}

    seq = session.next_event_seq
    for raw in payload.events:
        rest = {k: v for k, v in raw.items() if k not in ("t", "type", "item_ref")}
        db.add(models.Event(
            session_id=session.id,
            seq=seq,
            client_t=raw.get("t", 0.0),
            type=raw.get("type", "unknown"),
            item_ref=raw.get("item_ref"),
            payload=rest,
        ))
        seq += 1
    session.next_event_seq = seq
    session.last_batch_seq = payload.seq
    db.commit()
    return {"stored": len(payload.events)}


def _events_to_dicts(events: list[models.Event]) -> list[dict]:
    out = []
    for e in events:
        d = {"t": e.client_t, "type": e.type, **e.payload}
        if e.item_ref:
            d["item_ref"] = e.item_ref
        out.append(d)
    return out


def _seq_range(events: list[models.Event]) -> tuple[Optional[int], Optional[int]]:
    """Primer y último Event.seq de los eventos de origen (None, None si no hay eventos)."""
    if not events:
        return None, None
    seqs = [e.seq for e in events]
    return min(seqs), max(seqs)


def _create_indicator(db: DBSession, session_id: str, draft: IndicatorDraft, metrics_by_name: dict) -> None:
    indicator = models.Indicator(
        session_id=session_id,
        kind=draft.kind,
        level=models.IndicatorLevel(draft.level),
        description=draft.description,
        explanation=draft.explanation,
    )
    db.add(indicator)
    db.flush()  # necesita indicator.id para los links

    for name in draft.metric_names:
        metric = metrics_by_name.get(name)
        if metric is not None:
            db.add(models.IndicatorMetric(indicator_id=indicator.id, metric_id=metric.id))


def _run_processing(db: DBSession, session: models.Session) -> None:
    """Procesamiento determinístico (métricas + reglas) al finalizar la sesión (RF06). La
    comparación poblacional se hace al cerrar la evaluación (routers/exams.py, Incremento 16)."""
    events = db.query(models.Event).filter(models.Event.session_id == session.id).order_by(models.Event.seq).all()
    all_events = _events_to_dicts(events)

    features = compute_all_features(all_events)

    # P02: rango de Event.seq de origen de cada métrica (cap. 15, evento_desde/evento_hasta).
    desde, hasta = _seq_range(events)
    metrics_by_name: dict[str, models.Metric] = {}
    for name, value in features.items():
        metric = models.Metric(
            session_id=session.id, name=name, value=value, item_ref=None,
            evento_desde=desde, evento_hasta=hasta,
        )
        db.add(metric)
        metrics_by_name[name] = metric

    # Desglose por ítem, cuando los eventos traen item_ref (opcional, cap. 15 sección "Modelo de datos").
    item_refs = {e["item_ref"] for e in all_events if e.get("item_ref")}
    for item_ref in item_refs:
        item_events = [e for e in all_events if e.get("item_ref") == item_ref]
        item_features = compute_all_features(item_events)
        item_desde, item_hasta = _seq_range([e for e in events if e.item_ref == item_ref])
        for name, value in item_features.items():
            db.add(models.Metric(
                session_id=session.id, name=name, value=value, item_ref=item_ref,
                evento_desde=item_desde, evento_hasta=item_hasta,
            ))

    db.flush()  # asigna IDs a los Metric antes de linkearlos desde Indicator

    # Reglas al finalizar cada sesión. El modelo poblacional (Isolation Forest) ya no corre
    # acá: se aplica una sola vez al cerrar la evaluación, sobre la cohorte completa y con el
    # mismo protocolo para todas las sesiones (Incremento 16, processing/cohort.py).
    outcome = evaluate_session(features, None, rules_from_stored(session.policy.allowed_signals))

    for draft in outcome.drafts:
        _create_indicator(db, session.id, draft, metrics_by_name)

    session.needs_review = outcome.needs_review
    session.estado_modelo = "pendiente" if session.exam.cerrada_at is None else "no_evaluada"
    session.procesada_at = models.utcnow()
    db.commit()


def _clear_processing(db: DBSession, session: models.Session) -> None:
    """Borra métricas e indicadores de un procesamiento anterior (para reprocesar)."""
    ids = [i.id for i in session.indicators]
    if ids:
        db.query(models.ReviewIndicator).filter(models.ReviewIndicator.indicator_id.in_(ids)).delete(synchronize_session=False)
        db.query(models.IndicatorMetric).filter(models.IndicatorMetric.indicator_id.in_(ids)).delete(synchronize_session=False)
    db.query(models.Indicator).filter(models.Indicator.session_id == session.id).delete(synchronize_session=False)
    db.query(models.Metric).filter(models.Metric.session_id == session.id).delete(synchronize_session=False)
    db.flush()
    db.expire(session)


def process_session(db: DBSession, session: models.Session) -> bool:
    """Procesa (o reprocesa) una sesión finalizada. Devuelve False si falló; no deja datos a medias."""
    try:
        # Revisión del Incremento 16: dos procesamientos concurrentes de la misma sesión (doble
        # clic en "Entregar", o un /end en curso mientras el docente cierra la evaluación)
        # duplicaban métricas e indicadores. Se bloquea la fila de la sesión (FOR UPDATE en
        # PostgreSQL; SQLite serializa las escrituras) y se vuelve a leer `procesada_at`: si
        # otro request ya la procesó, no se reprocesa (ni se borran vínculos de revisiones).
        locked = (
            db.query(models.Session).filter(models.Session.id == session.id)
            .with_for_update().populate_existing().one()
        )
        if locked.procesada_at is not None:
            db.commit()
            return True
        _clear_processing(db, session)
        _run_processing(db, session)
        return True
    except Exception:  # noqa: BLE001 — se informa como procesamiento pendiente y se reintenta
        db.rollback()
        return False


@router.post("/sessions/{session_id}/end")
def end_session(
    session_id: str,
    payload: Optional[schemas.SessionEndRequest] = None,
    session: models.Session = Depends(get_session_by_token),
    db: DBSession = Depends(get_db),
):
    """
    Cierre de la sesión, idempotente (Incremento 16). El cliente puede repetirlo sin riesgo:
    - si la sesión estaba activa, se finaliza y se guarda la respuesta entregada;
    - si ya estaba finalizada pero su procesamiento no terminó, se reintenta;
    - si ya estaba finalizada y procesada, devuelve el mismo resultado.
    Solo con `procesada = true` el estudiante ve la entrega como confirmada.
    """
    respuesta = payload.respuesta if payload else None
    respuestas = payload.respuestas if payload else None
    if respuestas and not respuesta:
        respuesta = respuesta_completa(session.exam, respuestas)
    if session.status == models.SessionStatus.active:
        session.status = models.SessionStatus.ended
        session.ended_at = models.utcnow()
        # La respuesta se guarda solo en la entrega (transición activa -> finalizada). Antes
        # se aceptaba también en un /end posterior si la primera entrega no la traía: una
        # entrega tardía, incluso después del cierre de la evaluación.
        session.respuesta = respuesta
        session.respuestas = respuestas or None
    db.commit()

    if session.procesada_at is None and not process_session(db, session):
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "La sesión quedó finalizada pero su procesamiento no terminó; reintentá el cierre.",
        )
    db.refresh(session)
    return {"status": "ended", "needs_review": session.needs_review, "procesada": True}


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(
    session_id: str,
    db: DBSession = Depends(get_db),
    teacher: models.User = Depends(get_current_teacher),
):
    """RF17: el docente elimina una sesión (p. ej. a pedido del estudiante, por su código)."""
    session = _get_owned_session(db, teacher, session_id)
    delete_session_data(db, session)
    db.commit()
    return None


REVIEW_STATUSES = ("sin_revision", "revisada", "validacion_pendiente")


def _sorted_reviews(session: models.Session) -> list[models.Review]:
    return sorted(session.reviews, key=lambda r: r.created_at)


def _review_status(session: models.Session) -> tuple[str, Optional[models.Review]]:
    """
    Estado de revisión DERIVADO de la última revisión (RF11/HU08). Las revisiones
    son solo inserción: pedir validación adicional deja la sesión "pendiente" hasta
    que una revisión posterior la marque como revisada; nada se edita ni se borra.
    ImprontIA no ejecuta la validación (cap. 13): solo registra y lista el pedido.
    """
    reviews = _sorted_reviews(session)
    if not reviews:
        return "sin_revision", None
    last = reviews[-1]
    if last.action == models.ReviewAction.additional_validation:
        return "validacion_pendiente", last
    return "revisada", last


def _summary_fields(session: models.Session) -> dict:
    status_, last = _review_status(session)
    return dict(
        id=session.id,
        exam_id=session.exam_id,
        exam_name=session.exam.name,
        participant_id=session.participant_id,
        session_type=session.session_type,
        status=session.status.value,
        needs_review=session.needs_review,
        started_at=session.started_at,
        ended_at=session.ended_at,
        review_status=status_,
        estado_modelo=session.estado_modelo,
        last_review_at=last.created_at if last else None,
        last_review_notes=last.notes if last else None,
        indicadores=[
            dict(
                kind=i.kind,
                level=i.level.value if hasattr(i.level, "value") else str(i.level),
                prioriza=i.kind not in INFORMATIVE_KINDS and not (i.explanation or {}).get("permitido_por_reglas"),
            )
            for i in session.indicators
        ],
    )


def _review_out(review: models.Review) -> schemas.ReviewOut:
    return schemas.ReviewOut(
        id=review.id,
        action=review.action.value,
        notes=review.notes,
        indicator_ids=[link.indicator_id for link in review.indicator_links],
        created_at=review.created_at,
        teacher_email=review.teacher.email if review.teacher else None,
    )


@router.get("/sessions", response_model=list[schemas.SessionSummary])
def list_sessions(
    exam_id: Optional[str] = None,
    needs_review: Optional[bool] = None,
    review_status: Optional[str] = None,
    db: DBSession = Depends(get_db),
    teacher: models.User = Depends(get_current_teacher),
):
    """
    Sin `exam_id` lista las sesiones de TODAS las evaluaciones del docente; con
    `review_status=validacion_pendiente` es la vista de casos a profundizar (RF11/HU08).
    """
    if review_status is not None and review_status not in REVIEW_STATUSES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"review_status debe ser uno de {REVIEW_STATUSES}")

    # Revisión del Incremento 16 (RNF11): el resumen lee la evaluación y las revisiones de cada
    # sesión; sin carga anticipada eran 1 + 2N consultas (≈ 0,35 s con 500 sesiones y > 2 s
    # bajo carga). Ahora son 3 consultas.
    q = (
        db.query(models.Session).join(models.Exam).filter(models.Exam.teacher_id == teacher.id)
        .options(
            contains_eager(models.Session.exam),
            selectinload(models.Session.reviews),
            selectinload(models.Session.indicators),
        )
    )
    if exam_id:
        q = q.filter(models.Session.exam_id == exam_id)
    if needs_review is not None:
        q = q.filter(models.Session.needs_review == needs_review)
    summaries = [_summary_fields(s) for s in q.order_by(models.Session.started_at.desc()).all()]
    if review_status is not None:
        # Filtro en memoria sobre el estado derivado: suficiente para el volumen de un MVP
        # (una cátedra); con más volumen convendría materializarlo o resolverlo en SQL.
        summaries = [s for s in summaries if s["review_status"] == review_status]
    return [schemas.SessionSummary(**s) for s in summaries]


def _get_owned_session(db: DBSession, teacher: models.User, session_id: str) -> models.Session:
    session = (
        db.query(models.Session)
        .join(models.Exam)
        .filter(models.Session.id == session_id, models.Exam.teacher_id == teacher.id)
        .first()
    )
    if not session:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sesión no encontrada")
    return session


@router.get("/sessions/{session_id}", response_model=schemas.SessionDetail)
def get_session(
    session_id: str,
    db: DBSession = Depends(get_db),
    teacher: models.User = Depends(get_current_teacher),
):
    session = _get_owned_session(db, teacher, session_id)
    event_count = db.query(models.Event).filter(models.Event.session_id == session.id).count()

    indicators_out = [
        schemas.IndicatorOut(
            id=i.id,
            kind=i.kind,
            level=i.level.value,
            estado=i.estado,
            description=i.description,
            explanation=i.explanation,
            metric_ids=[im.metric_id for im in i.indicator_metrics],
            computed_at=i.computed_at,
        )
        for i in session.indicators
    ]

    return schemas.SessionDetail(
        **_summary_fields(session),
        context=session.context,
        metrics=[schemas.MetricOut.model_validate(m) for m in session.metrics],
        indicators=indicators_out,
        event_count=event_count,
        reviews=[_review_out(r) for r in _sorted_reviews(session)],
        procesada=session.procesada_at is not None,
        respuesta=session.respuesta,
        items=session.exam.items,
        respuestas=session.respuestas,
        tiene_pdf=session.exam.tiene_pdf,
    )


@router.post("/sessions/{session_id}/reviews", response_model=schemas.ReviewOut)
def create_review(
    session_id: str,
    payload: schemas.ReviewCreate,
    db: DBSession = Depends(get_db),
    teacher: models.User = Depends(get_current_teacher),
):
    """RF11: el docente deja constancia de su revisión / pedido de validación adicional."""
    session = _get_owned_session(db, teacher, session_id)

    try:
        action = models.ReviewAction(payload.action)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Acción de revisión inválida")

    valid_indicator_ids = {i.id for i in session.indicators}
    for indicator_id in payload.indicator_ids:
        if indicator_id not in valid_indicator_ids:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Indicador {indicator_id} no pertenece a esta sesión")

    review = models.Review(session_id=session.id, teacher_id=teacher.id, action=action, notes=payload.notes)
    db.add(review)
    db.flush()

    indicators_by_id = {i.id: i for i in session.indicators}
    for indicator_id in payload.indicator_ids:
        db.add(models.ReviewIndicator(review_id=review.id, indicator_id=indicator_id))
        indicators_by_id[indicator_id].estado = "atendido"  # P02: el docente ya lo miró

    db.commit()
    db.refresh(review)
    return _review_out(review)
