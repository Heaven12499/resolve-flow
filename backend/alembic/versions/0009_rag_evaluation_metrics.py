"""Store expanded RAG evaluation metrics."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0009_rag_eval_metrics"
down_revision: str | None = "0008_versioned_knowledge"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("knowledge_evaluation_runs", sa.Column("recall_at_1", sa.Float(), nullable=False, server_default="0"))
    op.add_column("knowledge_evaluation_runs", sa.Column("mrr", sa.Float(), nullable=False, server_default="0"))
    op.add_column("knowledge_evaluation_runs", sa.Column("no_answer_cases", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("knowledge_evaluation_runs", sa.Column("correct_rejection_cases", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("knowledge_evaluation_runs", "correct_rejection_cases")
    op.drop_column("knowledge_evaluation_runs", "no_answer_cases")
    op.drop_column("knowledge_evaluation_runs", "mrr")
    op.drop_column("knowledge_evaluation_runs", "recall_at_1")
