"""add bookings

Revision ID: 08657fbb9170
Revises: f03c574899d1
Create Date: 2026-08-28 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '08657fbb9170'
down_revision = 'f03c574899d1'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'bookings',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('session_id', sa.Text(), nullable=True),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('email', sa.Text(), nullable=False),
        sa.Column('phone', sa.Text(), nullable=True),
        sa.Column('meeting_type', sa.Text(), nullable=False, server_default='appointment'),
        sa.Column('start_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('end_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('calendar_event_id', sa.Text(), nullable=False),
        sa.Column('status', sa.Text(), nullable=False, server_default='confirmed'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_bookings_session_id', 'bookings', ['session_id'])


def downgrade():
    op.drop_index('ix_bookings_session_id', table_name='bookings')
    op.drop_table('bookings')
