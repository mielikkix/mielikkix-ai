"""account deletion scheduling + consent record pseudonymisation (GDPR Phase 4)

Revision ID: c4e8a2d6f1b3
Revises: b7d2e4f6a8c1
Create Date: 2026-09-26 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'c4e8a2d6f1b3'
down_revision = 'b7d2e4f6a8c1'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('businesses', sa.Column('deletion_requested_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('businesses', sa.Column('deletion_scheduled_for', sa.DateTime(timezone=True), nullable=True))
    op.create_index('ix_businesses_deletion_scheduled_for', 'businesses', ['deletion_scheduled_for'])

    op.add_column('consent_records', sa.Column('subject_hash', sa.Text(), nullable=True))
    op.add_column('consent_records', sa.Column('retain_until', sa.DateTime(timezone=True), nullable=True))
    op.create_index('ix_consent_records_subject_hash', 'consent_records', ['subject_hash'])
    op.alter_column('consent_records', 'user_id', nullable=True)
    op.drop_constraint('consent_records_user_id_fkey', 'consent_records', type_='foreignkey')
    op.create_foreign_key('consent_records_user_id_fkey', 'consent_records', 'users', ['user_id'], ['id'], ondelete='SET NULL')


def downgrade():
    op.drop_constraint('consent_records_user_id_fkey', 'consent_records', type_='foreignkey')
    # Pseudonymised rows have no user to point back to; they can't survive a
    # NOT NULL user_id, so they go.
    op.execute("DELETE FROM consent_records WHERE user_id IS NULL")
    op.create_foreign_key('consent_records_user_id_fkey', 'consent_records', 'users', ['user_id'], ['id'], ondelete='CASCADE')
    op.alter_column('consent_records', 'user_id', nullable=False)
    op.drop_index('ix_consent_records_subject_hash', table_name='consent_records')
    op.drop_column('consent_records', 'retain_until')
    op.drop_column('consent_records', 'subject_hash')

    op.drop_index('ix_businesses_deletion_scheduled_for', table_name='businesses')
    op.drop_column('businesses', 'deletion_scheduled_for')
    op.drop_column('businesses', 'deletion_requested_at')
