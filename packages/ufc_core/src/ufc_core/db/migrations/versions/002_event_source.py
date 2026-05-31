"""add event.source (promotion origin for ELO/training universe)

Revision ID: 002
Revises: 001
Create Date: 2026-06-13

Adds the ``event.source`` column so the lab can distinguish real UFC cards
("scraped"/"promoted") from non-UFC events ("fighter_history": PRIDE, Strikeforce,
ONE, ...) that only appear referenced in a fighter's history. Only UFC events feed
the ELO/training universe, matching the legacy backend. The column is backfilled
from the legacy backend by a backfill script; new rows
default to "scraped" since the lab scrapes UFC.
"""
from alembic import op
import sqlalchemy as sa

revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'event',
        sa.Column('source', sa.String(length=20), nullable=True,
                  server_default='scraped'),
    )


def downgrade() -> None:
    op.drop_column('event', 'source')
