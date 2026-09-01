"""Add source traceability for knowledge ingestion."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0005_knowledge_ingest"
down_revision: str | None = "0004_add_agent_runs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # A Docker restart can occur after MySQL applies one ALTER TABLE but before
    # Alembic writes its version row. Inspect first so this migration can safely
    # resume from such a partially applied state.
    inspector = sa.inspect(op.get_bind())
    existing_columns = {column["name"] for column in inspector.get_columns("knowledge_documents")}
    columns = (
        ("source_name", sa.Column("source_name", sa.String(length=255), nullable=True)),
        ("source_type", sa.Column("source_type", sa.String(length=30), nullable=False, server_default="manual")),
        ("source_metadata", sa.Column("source_metadata", sa.JSON(), nullable=True)),
        ("content_hash", sa.Column("content_hash", sa.String(length=64), nullable=True)),
        ("ingestion_status", sa.Column("ingestion_status", sa.String(length=20), nullable=False, server_default="published")),
    )
    for column_name, column in columns:
        if column_name not in existing_columns:
            op.add_column("knowledge_documents", column)

    existing_indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes("knowledge_documents")}
    if "ix_knowledge_documents_content_hash" not in existing_indexes:
        op.create_index("ix_knowledge_documents_content_hash", "knowledge_documents", ["content_hash"])
    if "ix_knowledge_documents_ingestion_status" not in existing_indexes:
        op.create_index("ix_knowledge_documents_ingestion_status", "knowledge_documents", ["ingestion_status"])


def downgrade() -> None:
    op.drop_index("ix_knowledge_documents_ingestion_status", table_name="knowledge_documents")
    op.drop_index("ix_knowledge_documents_content_hash", table_name="knowledge_documents")
    op.drop_column("knowledge_documents", "ingestion_status")
    op.drop_column("knowledge_documents", "content_hash")
    op.drop_column("knowledge_documents", "source_metadata")
    op.drop_column("knowledge_documents", "source_type")
    op.drop_column("knowledge_documents", "source_name")
