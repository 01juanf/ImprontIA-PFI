"""Etiqueta de condición de las sesiones de simulación (Fase 2, P03).

- `sessions.condicion_simulacion`: condición que declara quien rinde una sesión de
  prueba ("normal", "pegado", "transcripcion", "consulta_externa", "suplantacion").
  NULL en las sesiones reales y en todas las anteriores a esta migración. El docente
  no la ve y el pipeline no la lee; solo la usan los scripts de exportación y análisis.

Revision ID: 0003_condicion_simulacion
Revises: 0002_campos_er
Create Date: 2026-10-17
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_condicion_simulacion"
down_revision: Union[str, None] = "0002_campos_er"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("sessions") as batch:
        batch.add_column(sa.Column("condicion_simulacion", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("sessions") as batch:
        batch.drop_column("condicion_simulacion")
