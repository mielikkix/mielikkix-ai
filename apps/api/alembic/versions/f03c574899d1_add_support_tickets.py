"""add support tickets and ticket messages

Revision ID: f03c574899d1
Revises: c1d9f4a2b6e3
Create Date: 2026-08-27 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = 'f03c574899d1'
down_revision = 'c1d9f4a2b6e3'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'tickets',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('session_id', sa.Text(), nullable=False),
        sa.Column('channel', sa.Text(), nullable=False, server_default='web'),
        sa.Column('status', sa.Text(), nullable=False, server_default='open'),
        sa.Column('category', sa.Text(), nullable=True),
        sa.Column('priority', sa.Text(), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('customer_name', sa.Text(), nullable=True),
        sa.Column('customer_email', sa.Text(), nullable=True),
        sa.Column('customer_phone', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_tickets_session_id', 'tickets', ['session_id'])

    op.create_table(
        'ticket_messages',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('ticket_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tickets.id'), nullable=False),
        sa.Column('role', sa.Text(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_ticket_messages_ticket_id', 'ticket_messages', ['ticket_id'])


def downgrade():
    op.drop_index('ix_ticket_messages_ticket_id', table_name='ticket_messages')
    op.drop_table('ticket_messages')
    op.drop_index('ix_tickets_session_id', table_name='tickets')
    op.drop_table('tickets')
