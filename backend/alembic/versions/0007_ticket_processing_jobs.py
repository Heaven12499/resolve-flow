"""Add durable ticket processing jobs."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0007_ticket_jobs"
down_revision: str | None = "0006_rag_eval_runs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ticket_processing_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ticket_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"]),
    )
    op.create_index("ix_ticket_processing_jobs_ticket_id", "ticket_processing_jobs", ["ticket_id"], unique=True)
    op.create_index("ix_ticket_processing_jobs_status", "ticket_processing_jobs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_ticket_processing_jobs_status", table_name="ticket_processing_jobs")
    op.drop_index("ix_ticket_processing_jobs_ticket_id", table_name="ticket_processing_jobs")
    op.drop_table("ticket_processing_jobs")
