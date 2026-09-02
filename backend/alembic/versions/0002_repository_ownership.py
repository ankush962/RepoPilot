"""add repository ownership

Revision ID: 0002_repository_ownership
Revises: 0001_production_foundation
"""

from alembic import op
import sqlalchemy as sa


revision = "0002_repository_ownership"
down_revision = "0001_production_foundation"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "repositories",
        sa.Column("owner_username", sa.String(length=255), nullable=True),
    )

    op.execute(
        """
        UPDATE repositories
        SET owner_username = 'admin'
        WHERE owner_username IS NULL
        """
    )

    op.alter_column(
        "repositories",
        "owner_username",
        nullable=False,
    )

    op.create_index(
        "ix_repositories_owner_username",
        "repositories",
        ["owner_username"],
    )


def downgrade():
    op.drop_index(
        "ix_repositories_owner_username",
        table_name="repositories",
    )
    op.drop_column("repositories", "owner_username")
