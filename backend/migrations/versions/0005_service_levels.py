"""Service response evidence and isolated synthetic monitoring records.

Existing support deadlines and acknowledgements remain unknown: old messages
must not be relabelled as verified SLA responses by a schema migration.
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("is_monitoring", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("experiences", sa.Column("is_monitoring", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_index("ix_experiences_is_monitoring", "experiences", ["is_monitoring"])
    op.add_column("bookings", sa.Column("is_synthetic", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_index("ix_bookings_is_synthetic", "bookings", ["is_synthetic"])
    op.add_column("support_tickets", sa.Column("priority", sa.String(2), nullable=False, server_default="P3"))
    for name in ("response_due_at", "first_response_at"):
        op.add_column("support_tickets", sa.Column(name, sa.DateTime(timezone=True), nullable=True))
    op.add_column("support_tickets", sa.Column("first_response_by", sa.String(36), nullable=True))
    op.create_foreign_key("fk_support_first_response_by", "support_tickets", "users", ["first_response_by"], ["id"])
    op.add_column("support_tickets", sa.Column("response_working_seconds", sa.Integer(), nullable=True))
    op.add_column("support_tickets", sa.Column("response_calendar", sa.JSON(), nullable=True))
    op.create_check_constraint("ck_support_priority", "support_tickets", "priority IN ('P1','P2','P3')")
    op.create_check_constraint("ck_support_response_seconds", "support_tickets", "response_working_seconds IS NULL OR response_working_seconds >= 0")
    op.create_index("ix_support_response_due_priority", "support_tickets", ["response_due_at", "priority"])


def downgrade():
    raise RuntimeError("Restore a verified backup with its matching application version; SLA evidence is retained")
