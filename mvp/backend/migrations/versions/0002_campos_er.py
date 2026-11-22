"""Campos del modelo entidad-relación (cap. 15) que el código todavía no tenía.

- `policy_captures.retencion_dias`: plazo de conservación de eventos y métricas que
  declara la política (RNF10). NULL = sin plazo definido, como todas las políticas
  anteriores. Esta migración solo agrega el campo; la purga es otra tarea.
- `metrics.evento_desde` / `metrics.evento_hasta`: rango de `events.seq` sobre el que
  se calculó la métrica (RNF05: reconstruir el origen sin una tabla de unión). NULL en
  las métricas calculadas antes de esta migración.
- `indicators.estado`: si algún docente ya atendió el indicador en una revisión
  ("pendiente" | "atendido"). Los indicadores existentes quedan "pendiente" y se
  completan desde `review_indicators` (las revisiones existentes que los citan).

Ninguno cambia el cálculo: el pipeline, las reglas y el Isolation Forest no los leen.

Revision ID: 0002_campos_er
Revises: 0001_esquema_inicial
Create Date: 2026-10-16
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_campos_er"
down_revision: Union[str, None] = "0001_esquema_inicial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("policy_captures") as batch:
        batch.add_column(sa.Column("retencion_dias", sa.Integer(), nullable=True))
    with op.batch_alter_table("metrics") as batch:
        batch.add_column(sa.Column("evento_desde", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("evento_hasta", sa.Integer(), nullable=True))
    with op.batch_alter_table("indicators") as batch:
        batch.add_column(sa.Column("estado", sa.String(), nullable=False, server_default="pendiente"))

    # Indicadores que una revisión ya existente citó: quedan "atendido".
    op.execute(
        "UPDATE indicators SET estado = 'atendido' "
        "WHERE id IN (SELECT indicator_id FROM review_indicators)"
    )


def downgrade() -> None:
    with op.batch_alter_table("indicators") as batch:
        batch.drop_column("estado")
    with op.batch_alter_table("metrics") as batch:
        batch.drop_column("evento_hasta")
        batch.drop_column("evento_desde")
    with op.batch_alter_table("policy_captures") as batch:
        batch.drop_column("retencion_dias")
