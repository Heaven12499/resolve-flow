"""Persist resumable case-manager state."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0010_case_agent_state"
down_revision: str | None = "0009_rag_eval_metrics"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "case_agent_states",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ticket_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("goal", sa.String(length=500), nullable=False),
        sa.Column("state_data", sa.JSON(), nullable=False),
        sa.Column("pending_question", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_case_agent_states_ticket_id", "case_agent_states", ["ticket_id"], unique=True)
    op.create_index("ix_case_agent_states_status", "case_agent_states", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_case_agent_states_status", table_name="case_agent_states")
    op.drop_index("ix_case_agent_states_ticket_id", table_name="case_agent_states")
    op.drop_table("case_agent_states")
