"""Persist session revocation, private local mail and owned engagement records.

Revision ID: 0003
Revises: 0002
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def identifier():
    return sa.Column("id", sa.String(36), primary_key=True)


def timestamp(name="created_at", nullable=False):
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def user_fk(name="user_id", nullable=False, cascade=False):
    return sa.Column(name, sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE" if cascade else None), nullable=nullable)


def booking_fk(nullable=True):
    return sa.Column("booking_id", sa.String(36), sa.ForeignKey("bookings.id"), nullable=nullable)


def upgrade():
    op.create_table("revoked_access_tokens", identifier(), user_fk(cascade=True), timestamp("expires_at"), timestamp("revoked_at"))
    op.create_index("ix_revoked_access_tokens_user_id", "revoked_access_tokens", ["user_id"])
    op.create_index("ix_revoked_access_tokens_expires_at", "revoked_access_tokens", ["expires_at"])
    op.create_table("user_access_boundaries", sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True), timestamp("invalidated_at"))
    op.create_table("password_resets", identifier(), user_fk(cascade=True),
                    sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
                    sa.Column("credential_digest", sa.String(64), nullable=False),
                    timestamp("expires_at"), timestamp("used_at", nullable=True), timestamp())
    op.create_index("ix_password_resets_user_id", "password_resets", ["user_id"])
    op.create_index("ix_password_resets_expires_at", "password_resets", ["expires_at"])
    op.create_table("demo_emails", identifier(), sa.Column("recipient", sa.String(254), nullable=False),
                    sa.Column("subject", sa.String(200), nullable=False), sa.Column("body", sa.Text(), nullable=False), timestamp())
    op.create_index("ix_demo_emails_recipient", "demo_emails", ["recipient"])
    op.create_index("ix_demo_emails_created_at", "demo_emails", ["created_at"])
    op.create_table("notifications", identifier(), user_fk(cascade=True),
                    sa.Column("event", sa.String(80), nullable=False),
                    sa.Column("title", sa.String(200), nullable=False), sa.Column("body", sa.Text(), nullable=False),
                    sa.Column("title_en", sa.String(200), nullable=False), sa.Column("title_kk", sa.String(200), nullable=False),
                    sa.Column("body_en", sa.Text(), nullable=False), sa.Column("body_kk", sa.Text(), nullable=False),
                    booking_fk(), sa.Column("is_read", sa.Boolean(), nullable=False), timestamp())
    op.create_index("ix_notifications_user_read_created", "notifications", ["user_id", "is_read", "created_at"])
    op.create_table("saved_searches", identifier(), user_fk(cascade=True),
                    sa.Column("name", sa.String(120), nullable=False), sa.Column("filters", sa.JSON(), nullable=False), timestamp())
    op.create_index("ix_saved_searches_user_id", "saved_searches", ["user_id"])
    op.create_table("support_tickets", identifier(), user_fk(), user_fk("vendor_id", nullable=True), booking_fk(),
                    sa.Column("subject", sa.String(180), nullable=False), sa.Column("status", sa.String(20), nullable=False),
                    timestamp(), timestamp("updated_at"),
                    sa.CheckConstraint("status IN ('open','in_progress','resolved','closed')", name="ck_support_ticket_status"))
    for column in ("user_id", "vendor_id", "booking_id"):
        op.create_index("ix_support_tickets_" + column, "support_tickets", [column])
    op.create_table("support_messages", identifier(),
                    sa.Column("ticket_id", sa.String(36), sa.ForeignKey("support_tickets.id", ondelete="CASCADE"), nullable=False),
                    user_fk("author_id"), sa.Column("author_role", sa.String(20), nullable=False),
                    sa.Column("body", sa.Text(), nullable=False), timestamp())
    op.create_index("ix_support_messages_ticket_id", "support_messages", ["ticket_id"])
    op.create_table("reviews", identifier(),
                    sa.Column("booking_id", sa.String(36), sa.ForeignKey("bookings.id"), nullable=False, unique=True),
                    user_fk(), sa.Column("experience_id", sa.String(36), sa.ForeignKey("experiences.id"), nullable=False),
                    sa.Column("rating", sa.Integer(), nullable=False), sa.Column("title", sa.String(180), nullable=False),
                    sa.Column("text", sa.Text(), nullable=False), sa.Column("status", sa.String(20), nullable=False),
                    user_fk("moderated_by", nullable=True), timestamp("moderated_at", nullable=True), timestamp(),
                    sa.CheckConstraint("rating >= 1 AND rating <= 5", name="ck_reviews_rating"),
                    sa.CheckConstraint("status IN ('pending','approved','rejected')", name="ck_reviews_status"))
    op.create_index("ix_reviews_user_id", "reviews", ["user_id"])
    op.create_index("ix_reviews_experience_status", "reviews", ["experience_id", "status"])
    op.create_table("audit_logs", identifier(), user_fk("actor_id", nullable=True),
                    sa.Column("action", sa.String(100), nullable=False), sa.Column("resource_type", sa.String(80), nullable=False),
                    sa.Column("resource_id", sa.String(36), nullable=True), sa.Column("details", sa.JSON(), nullable=False), timestamp())
    op.create_index("ix_audit_logs_actor_id", "audit_logs", ["actor_id"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])
    # Independent historical demo counters are replaced by the review projection.
    op.execute("UPDATE experiences SET rating = 0, review_count = 0")


def downgrade():
    for table in ("audit_logs", "reviews", "support_messages", "support_tickets", "saved_searches", "notifications", "demo_emails", "password_resets", "user_access_boundaries", "revoked_access_tokens"):
        op.drop_table(table)
