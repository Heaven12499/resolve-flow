"""Store repeatable RAG evaluation results."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0006_rag_eval_runs"
down_revision: str | None = "0005_knowledge_ingest"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "knowledge_evaluation_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("total_cases", sa.Integer(), nullable=False),
        sa.Column("hit_cases", sa.Integer(), nullable=False),
        sa.Column("low_confidence_cases", sa.Integer(), nullable=False),
        sa.Column("recall_at_3", sa.Float(), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("knowledge_evaluation_runs")
