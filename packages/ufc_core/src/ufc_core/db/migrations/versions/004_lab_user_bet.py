"""add lab_user_bet table (single-tenant betting tracker)

Revision ID: 004
Revises: 003
Create Date: 2026-06-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '004'
down_revision = '003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'lab_user_bet',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('event_id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.Integer(), nullable=True),
        sa.Column('bet_type', sa.String(length=10), nullable=False),
        sa.Column('picks', JSONB(), nullable=False),
        sa.Column('combo_key', sa.Text(), nullable=False),
        sa.Column('combined_odds', sa.Float(), nullable=False),
        sa.Column('stake', sa.Float(), nullable=False),
        sa.Column('potential_return', sa.Float(), nullable=False),
        sa.Column('status', sa.String(length=12), nullable=False, server_default='pending'),
        sa.Column('actual_return', sa.Float(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('engine_snapshot', JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['event_id'], ['event.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['session_id'], ['prediction_session.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('event_id', 'combo_key', name='uq_lab_user_bet_event_combo'),
    )
    op.create_index('ix_lab_user_bet_event_id', 'lab_user_bet', ['event_id'])
    op.create_index('ix_lab_user_bet_session_id', 'lab_user_bet', ['session_id'])


def downgrade() -> None:
    op.drop_index('ix_lab_user_bet_session_id', table_name='lab_user_bet')
    op.drop_index('ix_lab_user_bet_event_id', table_name='lab_user_bet')
    op.drop_table('lab_user_bet')
