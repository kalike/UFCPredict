"""add hp_search_trial.metrics (per-trial CV / prod / realworld metrics)

Revision ID: 003
Revises: 002
Create Date: 2026-06-13

Adds the ``hp_search_trial.metrics`` JSONB column so the lab HP search can
persist the full per-trial metric set produced by the legacy backend-style 4-fold
temporal CV: mean_* (objective space), prod_* (last/production fold) and
realworld_* (held-out TTA eval), plus the is_pareto flag. Previously only the
scalar ``value`` (primary objective) was stored.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'hp_search_trial',
        sa.Column('metrics', JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('hp_search_trial', 'metrics')
