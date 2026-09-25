"""Initial PostgreSQL travel catalog, accounts, favorites and bookings.

Revision ID: 0001
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('destinations',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('slug', sa.String(length=100), nullable=False),
    sa.Column('name', sa.String(length=160), nullable=False),
    sa.Column('name_en', sa.String(length=160), nullable=False),
    sa.Column('name_kk', sa.String(length=160), nullable=False),
    sa.Column('country', sa.String(length=120), nullable=False),
    sa.Column('country_en', sa.String(length=120), nullable=False),
    sa.Column('country_kk', sa.String(length=120), nullable=False),
    sa.Column('continent', sa.String(length=30), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('description_en', sa.Text(), nullable=False),
    sa.Column('description_kk', sa.Text(), nullable=False),
    sa.Column('image_url', sa.String(length=2000), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('slug')
    )
    op.create_index(op.f('ix_destinations_continent'), 'destinations', ['continent'], unique=False)
    op.create_table('users',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('email', sa.String(length=254), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('role', sa.String(length=20), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("role IN ('traveler', 'vendor', 'admin')", name='ck_users_role'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_table('experiences',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('slug', sa.String(length=160), nullable=False),
    sa.Column('vendor_id', sa.String(length=36), nullable=False),
    sa.Column('destination_id', sa.String(length=36), nullable=False),
    sa.Column('title', sa.String(length=180), nullable=False),
    sa.Column('title_en', sa.String(length=180), nullable=False),
    sa.Column('title_kk', sa.String(length=180), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('description_en', sa.Text(), nullable=False),
    sa.Column('description_kk', sa.Text(), nullable=False),
    sa.Column('category', sa.String(length=30), nullable=False),
    sa.Column('duration_days', sa.Integer(), nullable=False),
    sa.Column('price_from', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('rating', sa.Numeric(precision=2, scale=1), nullable=False),
    sa.Column('review_count', sa.Integer(), nullable=False),
    sa.Column('image_url', sa.String(length=2000), nullable=False),
    sa.Column('is_published', sa.Boolean(), nullable=False),
    sa.Column('tags', sa.JSON(), nullable=False),
    sa.Column('tags_en', sa.JSON(), nullable=False),
    sa.Column('tags_kk', sa.JSON(), nullable=False),
    sa.Column('included', sa.JSON(), nullable=False),
    sa.Column('included_en', sa.JSON(), nullable=False),
    sa.Column('included_kk', sa.JSON(), nullable=False),
    sa.Column('excluded', sa.JSON(), nullable=False),
    sa.Column('excluded_en', sa.JSON(), nullable=False),
    sa.Column('excluded_kk', sa.JSON(), nullable=False),
    sa.Column('itinerary', sa.JSON(), nullable=False),
    sa.Column('itinerary_en', sa.JSON(), nullable=False),
    sa.Column('itinerary_kk', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("category IN ('Nature','Culture','Adventure','Food','Beach','City')", name='ck_experiences_category'),
    sa.CheckConstraint('duration_days >= 1 AND duration_days <= 90', name='ck_experiences_duration'),
    sa.CheckConstraint('price_from >= 1', name='ck_experiences_price'),
    sa.CheckConstraint('rating >= 0 AND rating <= 5', name='ck_experiences_rating'),
    sa.ForeignKeyConstraint(['destination_id'], ['destinations.id'], ),
    sa.ForeignKeyConstraint(['vendor_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('slug')
    )
    op.create_index(op.f('ix_experiences_category'), 'experiences', ['category'], unique=False)
    op.create_index(op.f('ix_experiences_destination_id'), 'experiences', ['destination_id'], unique=False)
    op.create_index(op.f('ix_experiences_is_published'), 'experiences', ['is_published'], unique=False)
    op.create_index(op.f('ix_experiences_vendor_id'), 'experiences', ['vendor_id'], unique=False)
    op.create_table('departures',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('experience_id', sa.String(length=36), nullable=False),
    sa.Column('start_date', sa.Date(), nullable=False),
    sa.Column('end_date', sa.Date(), nullable=False),
    sa.Column('capacity', sa.Integer(), nullable=False),
    sa.Column('price', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.CheckConstraint('capacity >= 1 AND capacity <= 1000', name='ck_departures_capacity'),
    sa.CheckConstraint('end_date >= start_date', name='ck_departures_dates'),
    sa.CheckConstraint('price >= 1', name='ck_departures_price'),
    sa.ForeignKeyConstraint(['experience_id'], ['experiences.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('experience_id', 'start_date', name='uq_departure_experience_date')
    )
    op.create_index(op.f('ix_departures_experience_id'), 'departures', ['experience_id'], unique=False)
    op.create_index(op.f('ix_departures_start_date'), 'departures', ['start_date'], unique=False)
    op.create_table('favorites',
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('experience_id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['experience_id'], ['experiences.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id', 'experience_id')
    )
    op.create_table('bookings',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('reference', sa.String(length=20), nullable=False),
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('departure_id', sa.String(length=36), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('travelers_count', sa.Integer(), nullable=False),
    sa.Column('total_amount', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('contact_name', sa.String(length=120), nullable=False),
    sa.Column('contact_email', sa.String(length=254), nullable=False),
    sa.Column('notes', sa.Text(), nullable=False),
    sa.Column('experience_snapshot', sa.JSON(), nullable=False),
    sa.Column('start_date', sa.Date(), nullable=False),
    sa.Column('end_date', sa.Date(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("status IN ('pending','confirmed','cancelled','completed')", name='ck_bookings_status'),
    sa.CheckConstraint('total_amount >= 1', name='ck_bookings_amount'),
    sa.CheckConstraint('travelers_count >= 1 AND travelers_count <= 20', name='ck_bookings_travelers'),
    sa.ForeignKeyConstraint(['departure_id'], ['departures.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('reference')
    )
    op.create_index('ix_bookings_departure_status', 'bookings', ['departure_id', 'status'], unique=False)
    op.create_index(op.f('ix_bookings_user_id'), 'bookings', ['user_id'], unique=False)
    op.create_table('booking_status_history',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('booking_id', sa.String(length=36), nullable=False),
    sa.Column('actor_id', sa.String(length=36), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['actor_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['booking_id'], ['bookings.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_booking_status_history_booking_id'), 'booking_status_history', ['booking_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_booking_status_history_booking_id'), table_name='booking_status_history')
    op.drop_table('booking_status_history')
    op.drop_index(op.f('ix_bookings_user_id'), table_name='bookings')
    op.drop_index('ix_bookings_departure_status', table_name='bookings')
    op.drop_table('bookings')
    op.drop_table('favorites')
    op.drop_index(op.f('ix_departures_start_date'), table_name='departures')
    op.drop_index(op.f('ix_departures_experience_id'), table_name='departures')
    op.drop_table('departures')
    op.drop_index(op.f('ix_experiences_vendor_id'), table_name='experiences')
    op.drop_index(op.f('ix_experiences_is_published'), table_name='experiences')
    op.drop_index(op.f('ix_experiences_destination_id'), table_name='experiences')
    op.drop_index(op.f('ix_experiences_category'), table_name='experiences')
    op.drop_table('experiences')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')
    op.drop_index(op.f('ix_destinations_continent'), table_name='destinations')
    op.drop_table('destinations')
