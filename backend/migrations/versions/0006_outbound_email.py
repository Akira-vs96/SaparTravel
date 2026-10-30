"""Transactional SMTP outbox; existing local messages remain private local records."""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "outbound_emails",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("recipient", sa.String(254), nullable=False),
        sa.Column("subject", sa.String(200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("state", sa.String(12), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(80), nullable=False),
        sa.Column("password_reset_id", sa.String(36), sa.ForeignKey("password_resets.id", ondelete="CASCADE"), nullable=True),
        sa.CheckConstraint("state IN ('pending','sent','failed','cancelled')", name="ck_outbound_email_state"),
        sa.CheckConstraint("attempts >= 0", name="ck_outbound_email_attempts"),
    )
    op.create_index("ix_outbound_email_pending", "outbound_emails", ["state", "next_attempt_at"])


def downgrade():
    op.drop_index("ix_outbound_email_pending", table_name="outbound_emails")
    op.drop_table("outbound_emails")
