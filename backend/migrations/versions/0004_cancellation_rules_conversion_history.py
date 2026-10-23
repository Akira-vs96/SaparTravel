"""Vendor cancellation terms.

Revision ID: 0004
Revises: 0003
"""
from uuid import uuid4
from decimal import Decimal
from datetime import datetime, timezone
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("experience_cancellation_rules",
        sa.Column("experience_id", sa.String(36), sa.ForeignKey("experiences.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("days_before", sa.Integer(), primary_key=True),
        sa.Column("refund_percent", sa.Integer(), nullable=False),
        sa.CheckConstraint("days_before BETWEEN 0 AND 3650 AND refund_percent BETWEEN 0 AND 100", name="ck_cancellation_rule_bounds"))


def downgrade():
    raise RuntimeError("Cancellation agreements must be preserved. Restore a verified backup for downgrade.")
