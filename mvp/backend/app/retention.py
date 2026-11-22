"""
Eliminación de datos (RF17) y purga por vencimiento del plazo de conservación (RNF10).
Incremento 16.

Qué se elimina de una sesión: sus eventos, métricas, indicadores, vínculos
indicador-métrica, revisiones y vínculos revisión-indicador, y la sesión misma (con la
respuesta entregada). Qué se conserva: la evaluación y las versiones de su política de
captura, que no contienen datos de estudiantes.

Al eliminar la cuenta de un docente se eliminan sus evaluaciones (con todas sus sesiones y
versiones de política) y su usuario. Las revisiones que ese docente hubiera registrado
sobre sesiones de evaluaciones ajenas no existen: el acceso está limitado al propietario.

La purga elimina las sesiones cuyo plazo de conservación venció: el `retencion_dias` de su
política o, si no declara ninguno, el tope de 12 meses (RNF10), contado desde la finalización
de la sesión (o desde su inicio si nunca se finalizó). Se ejecuta
al arrancar el backend y con `python -m scripts.purgar_vencidas` (tarea periódica).
"""
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session as DBSession

from . import models


def delete_session_data(db: DBSession, session: models.Session) -> None:
    """Elimina todo lo asociado a una sesión (sin commit)."""
    indicator_ids = [i.id for i in session.indicators]
    review_ids = [r.id for r in session.reviews]
    if review_ids:
        db.query(models.ReviewIndicator).filter(models.ReviewIndicator.review_id.in_(review_ids)).delete(synchronize_session=False)
    if indicator_ids:
        db.query(models.ReviewIndicator).filter(models.ReviewIndicator.indicator_id.in_(indicator_ids)).delete(synchronize_session=False)
        db.query(models.IndicatorMetric).filter(models.IndicatorMetric.indicator_id.in_(indicator_ids)).delete(synchronize_session=False)
    db.query(models.Review).filter(models.Review.session_id == session.id).delete(synchronize_session=False)
    db.query(models.Indicator).filter(models.Indicator.session_id == session.id).delete(synchronize_session=False)
    db.query(models.Metric).filter(models.Metric.session_id == session.id).delete(synchronize_session=False)
    db.query(models.Event).filter(models.Event.session_id == session.id).delete(synchronize_session=False)
    # Las colecciones de la sesión (reviews, indicators…) ya cargadas en memoria siguen apuntando
    # a filas borradas arriba con DELETE masivos; sin expirarlas, el flush intentaba desvincularlas
    # (UPDATE reviews …) y fallaba con StaleDataError si la sesión tenía revisiones.
    db.expire(session)
    db.delete(session)


def delete_exam_data(db: DBSession, exam: models.Exam) -> None:
    for s in list(exam.sessions):
        delete_session_data(db, s)
    db.flush()
    db.query(models.PolicyCapture).filter(models.PolicyCapture.exam_id == exam.id).delete(synchronize_session=False)
    db.query(models.ExamDocument).filter(models.ExamDocument.exam_id == exam.id).delete(synchronize_session=False)
    db.expire(exam)
    db.delete(exam)


def delete_teacher_account(db: DBSession, teacher: models.User) -> None:
    for exam in list(teacher.exams):
        delete_exam_data(db, exam)
    db.flush()
    db.delete(teacher)


def retention_days(policy: models.PolicyCapture) -> int:
    """Plazo efectivo: el que declara la política o, si no declara ninguno, el tope de RNF10
    (12 meses). Revisión del Incremento 16: antes una política sin plazo (todas las anteriores
    al Incremento 14) conservaba los datos sin límite."""
    return policy.retencion_dias or models.RETENCION_MAX_DIAS


def expired_sessions(db: DBSession, now: Optional[datetime] = None) -> list[models.Session]:
    """Sesiones vencidas. El plazo se cuenta desde la finalización; una sesión que nunca se
    finalizó (abandonada) se cuenta desde su inicio, para que tampoco quede sin límite."""
    now = now or models.utcnow()
    oldest = now - timedelta(days=1)  # ninguna sesión más nueva puede estar vencida (plazo >= 1 día)
    rows = (
        db.query(models.Session)
        .join(models.PolicyCapture, models.Session.policy_id == models.PolicyCapture.id)
        .filter(func.coalesce(models.Session.ended_at, models.Session.started_at) <= oldest)
        .all()
    )
    return [s for s in rows
            if (s.ended_at or s.started_at) + timedelta(days=retention_days(s.policy)) <= now]


def purge_expired(db: DBSession, now: Optional[datetime] = None) -> int:
    """Elimina las sesiones con el plazo de conservación vencido. Devuelve cuántas."""
    victims = expired_sessions(db, now)
    for s in victims:
        delete_session_data(db, s)
    db.commit()
    return len(victims)
