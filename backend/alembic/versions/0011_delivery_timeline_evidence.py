"""Add delivery SLA fields and structured ticket evidence."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0011_delivery_evidence"
down_revision: str | None = "0010_case_agent_state"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("shipped_at", sa.DateTime(), nullable=True))
    op.add_column("orders", sa.Column("promised_delivery_at", sa.DateTime(), nullable=True))
    op.create_table(
        "ticket_evidence",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ticket_id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=True),
        sa.Column("message_id", sa.Integer(), nullable=True),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("media_type", sa.String(length=100), nullable=False),
        sa.Column("storage_uri", sa.String(length=500), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("uploaded_by", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["message_id"], ["ticket_messages.id"]),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ticket_id", "sha256", name="uq_ticket_evidence_ticket_sha256"),
    )
    op.create_index("ix_ticket_evidence_ticket_id", "ticket_evidence", ["ticket_id"])
    op.create_index("ix_ticket_evidence_order_id", "ticket_evidence", ["order_id"])
    op.create_index("ix_ticket_evidence_message_id", "ticket_evidence", ["message_id"])


def downgrade() -> None:
    op.drop_index("ix_ticket_evidence_message_id", table_name="ticket_evidence")
    op.drop_index("ix_ticket_evidence_order_id", table_name="ticket_evidence")
    op.drop_index("ix_ticket_evidence_ticket_id", table_name="ticket_evidence")
    op.drop_table("ticket_evidence")
    op.drop_column("orders", "promised_delivery_at")
    op.drop_column("orders", "shipped_at")
