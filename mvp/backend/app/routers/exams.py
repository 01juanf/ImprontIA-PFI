from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from sqlalchemy.orm import Session as DBSession

from .. import models, schemas
from ..auth import get_current_teacher
from ..database import get_db
from ..processing.anomaly import CONTINUOUS_METRICS
from ..processing.cohort import analizar_cohorte
from ..processing.indicators import INFORMATIVE_KINDS, indicator_from_anomaly
from ..processing.panorama import PANORAMA_METRICS, compute_panorama
from ..processing.rules import capture_signals, to_stored
from ..retention import delete_exam_data
from .sessions import MAX_PDF_BYTES, pdf_response

router = APIRouter(prefix="/exams", tags=["exams"])


def _stored_signals(payload) -> list[str]:
    """Señales + reglas del examen (Incremento 12) en el mismo JSON, sin cambio de esquema."""
    return to_stored(
        payload.allowed_signals,
        {"permite_pegado": payload.permite_pegado, "permite_otras_pestanas": payload.permite_otras_pestanas},
    )


@router.get("/{join_code}/info", response_model=schemas.ExamPublicInfo)
def get_exam_public_info(join_code: str, db: DBSession = Depends(get_db)):
    """
    Endpoint público (sin auth): lo consulta el frontend del estudiante ANTES
    de que consienta, para cumplir RF01/RF02 ("informar antes de iniciar").
    Siempre refleja la política VIGENTE (la más reciente), no una ya fijada
    a una sesión — el fijado ocurre recién en /sessions/start.
    """
    exam = db.query(models.Exam).filter(models.Exam.join_code == join_code.upper()).first()
    if not exam or not exam.current_policy:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Código de examen no encontrado")
    policy = exam.current_policy
    return schemas.ExamPublicInfo(
        name=exam.name,
        info_text=policy.info_text,
        rules_text=policy.rules_text,
        allowed_signals=capture_signals(policy.allowed_signals),
        cerrada=exam.cerrada_at is not None,
    )


@router.post("", response_model=schemas.ExamOut)
def create_exam(
    payload: schemas.ExamCreate,
    db: DBSession = Depends(get_db),
    teacher: models.User = Depends(get_current_teacher),
):
    items = [i.model_dump() for i in payload.items] if payload.items else None
    if items and len({i["id"] for i in items}) != len(items):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Los ejercicios deben tener identificadores distintos")
    exam = models.Exam(teacher_id=teacher.id, name=payload.name, prompt_text=payload.prompt_text, items=items)
    db.add(exam)
    db.flush()  # necesita exam.id para la política inicial

    policy = models.PolicyCapture(
        exam_id=exam.id,
        info_text=payload.info_text,
        rules_text=payload.rules_text,
        allowed_signals=_stored_signals(payload),
        retencion_dias=payload.retencion_dias,  # P02: opcional, None = sin plazo
    )
    db.add(policy)
    db.commit()
    db.refresh(exam)
    return exam


@router.get("", response_model=list[schemas.ExamOut])
def list_exams(
    db: DBSession = Depends(get_db),
    teacher: models.User = Depends(get_current_teacher),
):
    return db.query(models.Exam).filter(models.Exam.teacher_id == teacher.id).all()


@router.get("/{exam_id}", response_model=schemas.ExamOut)
def get_exam(
    exam_id: str,
    db: DBSession = Depends(get_db),
    teacher: models.User = Depends(get_current_teacher),
):
    exam = db.query(models.Exam).filter(
        models.Exam.id == exam_id, models.Exam.teacher_id == teacher.id
    ).first()
    if not exam:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Evaluación no encontrada")
    return exam


@router.delete("/{exam_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_exam(
    exam_id: str,
    db: DBSession = Depends(get_db),
    teacher: models.User = Depends(get_current_teacher),
):
    """
    RF17: el docente elimina una evaluación propia con todas sus sesiones, eventos, métricas,
    indicadores, revisiones y versiones de política (app/retention.py). No se puede deshacer.
    Una evaluación ajena responde 404, igual que una inexistente.
    """
    exam = db.query(models.Exam).filter(
        models.Exam.id == exam_id, models.Exam.teacher_id == teacher.id
    ).first()
    if not exam:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Evaluación no encontrada")
    delete_exam_data(db, exam)
    db.commit()
    return None


@router.post("/{exam_id}/policy", response_model=schemas.PolicyOut)
def update_policy(
    exam_id: str,
    payload: schemas.PolicyUpdate,
    db: DBSession = Depends(get_db),
    teacher: models.User = Depends(get_current_teacher),
):
    """
    Crea una NUEVA versión de política (RNF04) — nunca edita la vigente.
    Las sesiones ya iniciadas siguen referenciando su snapshot original.
    """
    exam = db.query(models.Exam).filter(
        models.Exam.id == exam_id, models.Exam.teacher_id == teacher.id
    ).first()
    if not exam:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Evaluación no encontrada")

    policy = models.PolicyCapture(
        exam_id=exam.id,
        info_text=payload.info_text,
        rules_text=payload.rules_text,
        allowed_signals=_stored_signals(payload),
        retencion_dias=payload.retencion_dias,  # P02: opcional, None = sin plazo
    )
    db.add(policy)
    db.commit()
    db.refresh(policy)
    return policy


@router.get("/{exam_id}/panorama", response_model=schemas.PanoramaOut)
def get_exam_panorama(
    exam_id: str,
    db: DBSession = Depends(get_db),
    teacher: models.User = Depends(get_current_teacher),
):
    """
    Panorama de la evaluación (Incremento 12, R1): cómo transcurrió en conjunto.
    Solo lee Metric/Indicator que el pipeline ya guardó al finalizar cada sesión.
    """
    exam = db.query(models.Exam).filter(
        models.Exam.id == exam_id, models.Exam.teacher_id == teacher.id
    ).first()
    if not exam:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Evaluación no encontrada")

    sessions = (
        db.query(models.Session)
        .filter(models.Session.exam_id == exam.id, models.Session.status == models.SessionStatus.ended)
        .all()
    )
    ids = [s.id for s in sessions]
    # Incremento 16: duración real de la sesión (inicio a fin, según el servidor), distinta del
    # período con eventos registrados (`session_duration_ms`).
    metrics_by_session: dict[str, dict[str, float]] = {
        s.id: ({"session_wall_duration_ms": (s.ended_at - s.started_at).total_seconds() * 1000}
               if s.ended_at and s.started_at else {})
        for s in sessions
    }
    indicators: list[dict] = []
    if ids:
        rows = (
            db.query(models.Metric)
            .filter(
                models.Metric.session_id.in_(ids),
                models.Metric.item_ref.is_(None),
                models.Metric.name.in_(PANORAMA_METRICS),
            )
            .all()
        )
        for r in rows:
            metrics_by_session[r.session_id][r.name] = r.value
        for ind in db.query(models.Indicator).filter(models.Indicator.session_id.in_(ids)).all():
            indicators.append({"session_id": ind.session_id, "kind": ind.kind, "explanation": ind.explanation})

    data = compute_panorama(metrics_by_session, indicators, {s.id: bool(s.needs_review) for s in sessions})
    estados = [s.estado_modelo for s in sessions]
    cobertura = schemas.PanoramaCobertura(
        evaluacion_cerrada=exam.cerrada_at is not None,
        sesiones_evaluadas=sum(e in ("sin_marca", "con_marca") for e in estados),
        sesiones_no_evaluadas=estados.count("no_evaluada"),
        sesiones_pendientes=estados.count("pendiente"),
    )
    return schemas.PanoramaOut(exam_id=exam.id, cobertura=cobertura, **data)


@router.post("/{exam_id}/cerrar", response_model=schemas.ExamOut)
def close_exam(
    exam_id: str,
    db: DBSession = Depends(get_db),
    teacher: models.User = Depends(get_current_teacher),
):
    """
    Cierra la evaluación y ejecuta el análisis poblacional sobre la cohorte completa
    (Incremento 16). Todas las sesiones finalizadas se analizan con un único modelo y el
    mismo protocolo; el resultado no depende del orden en que se entregaron. Después del
    cierre no se admiten sesiones nuevas. Repetir el cierre no cambia nada.
    """
    exam = db.query(models.Exam).filter(
        models.Exam.id == exam_id, models.Exam.teacher_id == teacher.id
    ).first()
    if not exam:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Evaluación no encontrada")
    if exam.cerrada_at is not None:
        return exam

    # Revisión del Incremento 16: el cierre se reclama con un UPDATE condicional y se confirma
    # ANTES del análisis. Así dos cierres concurrentes no analizan dos veces la cohorte (lo que
    # duplicaba los indicadores del modelo) y no se admiten sesiones nuevas mientras corre.
    claimed = (
        db.query(models.Exam)
        .filter(models.Exam.id == exam.id, models.Exam.cerrada_at.is_(None))
        .update({models.Exam.cerrada_at: models.utcnow()}, synchronize_session=False)
    )
    db.commit()
    db.refresh(exam)
    if not claimed:
        return exam  # otro request la cerró (o la está cerrando)
    try:
        _analyze_cohort(db, exam)
    except Exception:  # noqa: BLE001 — se reabre para que el docente pueda reintentar el cierre
        db.rollback()
        db.query(models.Exam).filter(models.Exam.id == exam.id).update(
            {models.Exam.cerrada_at: None}, synchronize_session=False)
        db.commit()
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "No se pudo completar el análisis de la cohorte; la evaluación sigue abierta.")
    db.refresh(exam)
    return exam


def _analyze_cohort(db: DBSession, exam: models.Exam) -> None:
    from .sessions import _create_indicator, process_session  # evita import circular

    ended = [s for s in exam.sessions if s.status == models.SessionStatus.ended]
    for s in ended:  # procesamientos pendientes (cierre de sesión que falló): se recuperan acá
        if s.procesada_at is None:
            process_session(db, s)
    ended = [s for s in ended if s.procesada_at is not None]

    metrics = {s.id: {} for s in ended}
    rows = (
        db.query(models.Metric)
        .filter(models.Metric.session_id.in_(list(metrics)), models.Metric.item_ref.is_(None),
                models.Metric.name.in_(CONTINUOUS_METRICS))
        .all()
    ) if metrics else []
    for r in rows:
        metrics[r.session_id][r.name] = r.value

    resultados = analizar_cohorte(metrics)
    for s in ended:
        # Indicadores del modelo de un protocolo anterior (sesiones previas al Incremento 16)
        # que ningún docente citó: se reemplazan por los del análisis de la cohorte.
        for ind in list(s.indicators):
            if ind.kind == "atipico_modelo_poblacional" and not ind.review_links:
                db.query(models.IndicatorMetric).filter(models.IndicatorMetric.indicator_id == ind.id).delete(synchronize_session=False)
                db.delete(ind)
        db.flush()
        result = resultados.get(s.id)
        draft = indicator_from_anomaly(result) if result is not None else None
        if draft:
            by_name = {m.name: m for m in s.metrics if m.item_ref is None}
            _create_indicator(db, s.id, draft, by_name)
        s.estado_modelo = "no_evaluada" if result is None else ("con_marca" if draft else "sin_marca")
        db.flush()
        db.refresh(s)
        # Prioriza la revisión todo indicador que no sea informativo ni esté permitido por las reglas.
        s.needs_review = any(
            i.kind not in INFORMATIVE_KINDS and not (i.explanation or {}).get("permitido_por_reglas")
            for i in s.indicators
        )
    db.commit()


def _owned_exam(db: DBSession, teacher: models.User, exam_id: str) -> models.Exam:
    exam = db.query(models.Exam).filter(models.Exam.id == exam_id, models.Exam.teacher_id == teacher.id).first()
    if not exam:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Evaluación no encontrada")
    return exam


@router.put("/{exam_id}/pdf", response_model=schemas.ExamOut)
async def upload_exam_pdf(
    exam_id: str,
    archivo: UploadFile = File(...),
    db: DBSession = Depends(get_db),
    teacher: models.User = Depends(get_current_teacher),
):
    """Enunciado del examen en PDF (nov. 2026). Reemplaza el anterior; hasta 4 MB (MAX_PDF_BYTES)."""
    exam = _owned_exam(db, teacher, exam_id)
    contenido = await archivo.read(MAX_PDF_BYTES + 1)
    if len(contenido) > MAX_PDF_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "El PDF supera los 4 MB")
    if not contenido.startswith(b"%PDF-"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "El archivo no es un PDF")
    nombre = (archivo.filename or "enunciado.pdf").replace('"', "").replace("\n", " ")[:200]
    doc = db.query(models.ExamDocument).filter(models.ExamDocument.exam_id == exam.id).first()
    if doc:
        doc.nombre, doc.contenido, doc.created_at = nombre, contenido, models.utcnow()
    else:
        db.add(models.ExamDocument(exam_id=exam.id, nombre=nombre, contenido=contenido))
    db.commit()
    db.refresh(exam)
    return exam


@router.get("/{exam_id}/pdf")
def get_exam_pdf(
    exam_id: str,
    db: DBSession = Depends(get_db),
    teacher: models.User = Depends(get_current_teacher),
) -> Response:
    exam = _owned_exam(db, teacher, exam_id)
    return pdf_response(db, exam.id)
