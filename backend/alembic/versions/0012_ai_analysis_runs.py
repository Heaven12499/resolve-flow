"""Add durable AI snapshot analysis runs."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0012_ai_analysis_runs"
down_revision: str | None = "0011_delivery_evidence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_analysis_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.String(length=64), nullable=False),
        sa.Column("ticket_id", sa.Integer(), nullable=False),
        sa.Column("business_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("provider", sa.String(length=30), nullable=True),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column("input_data", sa.JSON(), nullable=False),
        sa.Column("output_data", sa.JSON(), nullable=True),
        sa.Column("error", sa.String(length=500), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_analysis_runs_task_id", "ai_analysis_runs", ["task_id"], unique=True)
    op.create_index("ix_ai_analysis_runs_ticket_id", "ai_analysis_runs", ["ticket_id"])
    op.create_index("ix_ai_analysis_runs_status", "ai_analysis_runs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_ai_analysis_runs_status", table_name="ai_analysis_runs")
    op.drop_index("ix_ai_analysis_runs_ticket_id", table_name="ai_analysis_runs")
    op.drop_index("ix_ai_analysis_runs_task_id", table_name="ai_analysis_runs")
    op.drop_table("ai_analysis_runs")
