"""Initial evidence-first accounting schema.

Revision ID: 20260831_0001
Revises: None
"""

from alembic import op
from app.db import models  # noqa: F401
from app.db.base import Base

revision = "20260831_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
