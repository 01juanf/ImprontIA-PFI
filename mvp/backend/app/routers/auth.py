from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session as DBSession

from .. import models, schemas
from ..auth import create_access_token, get_current_teacher, verify_password
from ..database import get_db
from ..retention import delete_teacher_account

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=schemas.TokenResponse)
def login(payload: schemas.LoginRequest, db: DBSession = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Credenciales inválidas")
    return schemas.TokenResponse(access_token=create_access_token(user.id))


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(
    payload: schemas.AccountDeleteRequest,
    db: DBSession = Depends(get_db),
    teacher: models.User = Depends(get_current_teacher),
):
    """
    RF17 (Incremento 16): el docente elimina su cuenta. Se borran sus evaluaciones con todas
    sus sesiones, eventos, métricas, indicadores y revisiones. Pide la contraseña para
    confirmar, porque la operación no se puede deshacer.
    """
    if not verify_password(payload.password, teacher.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Contraseña incorrecta")
    delete_teacher_account(db, teacher)
    db.commit()
    return None
