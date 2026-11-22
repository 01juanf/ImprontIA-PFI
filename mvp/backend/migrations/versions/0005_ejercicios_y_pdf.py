"""Ejercicios múltiples y enunciado en PDF (rediseño, nov. 2026).

- `exams.items`: ejercicios del examen, [{"id": "1", "enunciado": "..."}]. NULL = una sola consigna.
- `exam_documents`: el PDF del enunciado (uno por evaluación, opcional).
- `sessions.respuestas`: respuestas por ejercicio, {"1": "...", ...}.

Revision ID: 0005_ejercicios_y_pdf
Revises: 0004_cierre_y_entrega
Create Date: 2026-11-09
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0005_ejercicios_y_pdf"
down_revision: Union[str, None] = "0004_cierre_y_entrega"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JSONType = JSONB().with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    with op.batch_alter_table("exams") as batch:
        batch.add_column(sa.Column("items", JSONType, nullable=True))
    with op.batch_alter_table("sessions") as batch:
        batch.add_column(sa.Column("respuestas", JSONType, nullable=True))
    op.create_table(
        "exam_documents",
        sa.Column("exam_id", sa.String(), sa.ForeignKey("exams.id"), primary_key=True),
        sa.Column("nombre", sa.String(), nullable=False),
        sa.Column("contenido", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("exam_documents")
    with op.batch_alter_table("sessions") as batch:
        batch.drop_column("respuestas")
    with op.batch_alter_table("exams") as batch:
        batch.drop_column("items")
