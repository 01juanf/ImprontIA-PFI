"""Cierre de la evaluación, estado del análisis poblacional y entrega (Incremento 16).

- `exams.cerrada_at`: momento del cierre; al cerrar se analiza la cohorte completa.
- `sessions.procesada_at`: fin del procesamiento; NULL con la sesión finalizada indica un
  procesamiento pendiente que se reintenta (cierre de sesión idempotente).
- `sessions.estado_modelo`: "pendiente" | "no_evaluada" | "sin_marca" | "con_marca".
  Todas las sesiones existentes quedan "pendiente": se analizan con el protocolo nuevo
  cuando se cierre su evaluación.
- `sessions.respuesta`: respuesta entregada por el estudiante (no la lee el procesamiento).

Revision ID: 0004_cierre_y_entrega
Revises: 0003_condicion_simulacion
Create Date: 2026-10-17
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_cierre_y_entrega"
down_revision: Union[str, None] = "0003_condicion_simulacion"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("exams") as batch:
        batch.add_column(sa.Column("cerrada_at", sa.DateTime(), nullable=True))
    with op.batch_alter_table("sessions") as batch:
        batch.add_column(sa.Column("procesada_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("estado_modelo", sa.String(), nullable=False, server_default="pendiente"))
        batch.add_column(sa.Column("respuesta", sa.Text(), nullable=True))
    # Sesiones ya procesadas antes de esta migración (tienen métricas): se marcan procesadas.
    op.execute(
        "UPDATE sessions SET procesada_at = ended_at "
        "WHERE ended_at IS NOT NULL AND id IN (SELECT session_id FROM metrics)"
    )


def downgrade() -> None:
    with op.batch_alter_table("sessions") as batch:
        batch.drop_column("respuesta")
        batch.drop_column("estado_modelo")
        batch.drop_column("procesada_at")
    with op.batch_alter_table("exams") as batch:
        batch.drop_column("cerrada_at")
