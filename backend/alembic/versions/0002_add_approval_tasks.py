"""Add approval tasks for controlled compensation."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0002_add_approval_tasks"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "approval_tasks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ticket_id", sa.Integer(), nullable=False),
        sa.Column("task_type", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("proposed_data", sa.JSON(), nullable=False),
        sa.Column("decision_data", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"]),
    )
    op.create_index("ix_approval_tasks_ticket_id", "approval_tasks", ["ticket_id"])
    op.create_index("ix_approval_tasks_status", "approval_tasks", ["status"])


def downgrade() -> None:
    op.drop_table("approval_tasks")
