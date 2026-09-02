"""Add versioned knowledge index metadata for atomic read switching."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0008_versioned_knowledge"
down_revision: str | None = "0007_ticket_jobs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("knowledge_chunks", sa.Column("index_generation", sa.String(length=40), nullable=False, server_default="legacy"))
    op.create_index("ix_knowledge_chunks_index_generation", "knowledge_chunks", ["index_generation"])
    op.create_table(
        "knowledge_index_states",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("collection_name", sa.String(length=100), nullable=False),
        sa.Column("generation", sa.String(length=40), nullable=False),
        sa.Column("document_count", sa.Integer(), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("collection_name"),
        sa.UniqueConstraint("generation"),
    )


def downgrade() -> None:
    op.drop_table("knowledge_index_states")
    op.drop_index("ix_knowledge_chunks_index_generation", table_name="knowledge_chunks")
    op.drop_column("knowledge_chunks", "index_generation")
