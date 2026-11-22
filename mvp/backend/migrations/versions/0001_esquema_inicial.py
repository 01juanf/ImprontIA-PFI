"""Esquema inicial: el que creaba `Base.metadata.create_all` hasta el Incremento 13.

Es la línea de base de las migraciones (Fase 2, P02). Reproduce tabla por tabla el
esquema que el backend creaba sin Alembic, así que una base creada antes de P02 se
marca en esta revisión (`stamp`) y después se le aplican las siguientes sin perder
datos (ver app/db_migrations.py). Verificado comparando `pg_dump -s` y el esquema de
SQLite contra el de `create_all` (bitácora, Incremento 14).

Revision ID: 0001_esquema_inicial
Revises:
Create Date: 2026-10-16
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_esquema_inicial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Mismo tipo que app/models.py: JSONB en PostgreSQL, JSON en SQLite.
JSONType = postgresql.JSONB().with_variant(sa.JSON(), "sqlite")

user_role = sa.Enum("docente", name="userrole")
session_status = sa.Enum("active", "ended", name="sessionstatus")
indicator_level = sa.Enum("low", "medium", "high", name="indicatorlevel")
review_action = sa.Enum("marked_reviewed", "additional_validation", name="reviewaction")


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("role", user_role, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "exams",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("teacher_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("join_code", sa.String(), nullable=False),
        sa.Column("prompt_text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["teacher_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("join_code"),
    )

    op.create_table(
        "policy_captures",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("exam_id", sa.String(), nullable=False),
        sa.Column("info_text", sa.Text(), nullable=False),
        sa.Column("rules_text", sa.Text(), nullable=False),
        sa.Column("allowed_signals", JSONType, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["exam_id"], ["exams.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "sessions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("exam_id", sa.String(), nullable=False),
        sa.Column("policy_id", sa.String(), nullable=False),
        sa.Column("participant_id", sa.String(), nullable=False),
        sa.Column("session_type", sa.String(), nullable=False),
        sa.Column("status", session_status, nullable=False),
        sa.Column("context", JSONType, nullable=False),
        sa.Column("session_token", sa.String(), nullable=False),
        sa.Column("consent_given", sa.Boolean(), nullable=False),
        sa.Column("needs_review", sa.Boolean(), nullable=False),
        sa.Column("next_event_seq", sa.Integer(), nullable=False),
        sa.Column("last_batch_seq", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["exam_id"], ["exams.id"]),
        sa.ForeignKeyConstraint(["policy_id"], ["policy_captures.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_token"),
    )

    op.create_table(
        "events",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("client_t", sa.Float(), nullable=False),
        sa.Column("server_received_at", sa.DateTime(), nullable=True),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("item_ref", sa.String(), nullable=True),
        sa.Column("payload", JSONType, nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_events_session_id", "events", ["session_id"], unique=False)

    op.create_table(
        "metrics",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("item_ref", sa.String(), nullable=True),
        sa.Column("computed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "indicators",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("level", indicator_level, nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("explanation", JSONType, nullable=False),
        sa.Column("computed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "indicator_metrics",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("indicator_id", sa.String(), nullable=False),
        sa.Column("metric_id", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["indicator_id"], ["indicators.id"]),
        sa.ForeignKeyConstraint(["metric_id"], ["metrics.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "reviews",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("teacher_id", sa.String(), nullable=False),
        sa.Column("action", review_action, nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"]),
        sa.ForeignKeyConstraint(["teacher_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "review_indicators",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("review_id", sa.String(), nullable=False),
        sa.Column("indicator_id", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["review_id"], ["reviews.id"]),
        sa.ForeignKeyConstraint(["indicator_id"], ["indicators.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    for table in ("review_indicators", "reviews", "indicator_metrics", "indicators", "metrics"):
        op.drop_table(table)
    op.drop_index("ix_events_session_id", table_name="events")
    for table in ("events", "sessions", "policy_captures", "exams"):
        op.drop_table(table)
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
    bind = op.get_bind()
    for enum in (review_action, indicator_level, session_status, user_role):
        enum.drop(bind, checkfirst=True)
