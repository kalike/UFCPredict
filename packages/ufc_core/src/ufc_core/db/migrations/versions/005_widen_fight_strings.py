"""widen fight.weight_class and fight.method to 255

Revision ID: 005
Revises: 004
Create Date: 2026-08-25

UFCStats emits weight-class strings longer than 50 chars (e.g. TUF tournament
title bouts: "Ultimate Fighter 28 Heavyweight Tournament Title Bout"), which
made the fighter ingest fail with StringDataRightTruncation on varchar(50).
Widen both free-text fight columns to 255 to absorb any current or future
label the scraper returns verbatim.
"""
from alembic import op
import sqlalchemy as sa

revision = '005'
down_revision = '004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column('fight', 'weight_class',
                    existing_type=sa.String(length=50),
                    type_=sa.String(length=255),
                    existing_nullable=True)
    op.alter_column('fight', 'method',
                    existing_type=sa.String(length=50),
                    type_=sa.String(length=255),
                    existing_nullable=True)


def downgrade() -> None:
    op.alter_column('fight', 'method',
                    existing_type=sa.String(length=255),
                    type_=sa.String(length=50),
                    existing_nullable=True)
    op.alter_column('fight', 'weight_class',
                    existing_type=sa.String(length=255),
                    type_=sa.String(length=50),
                    existing_nullable=True)
