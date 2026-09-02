"""make repository url unique per owner

Revision ID: 0003_repository_owner_url_unique
Revises: 0002_repository_ownership
"""

from alembic import op


revision = "0003_repository_owner_url_unique"
down_revision = "0002_repository_ownership"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE repositories
        DROP CONSTRAINT IF EXISTS repositories_url_key
    """)
    op.execute("""
        DROP INDEX IF EXISTS ix_repositories_url
    """)
    op.create_unique_constraint(
        "uq_repositories_owner_url",
        "repositories",
        ["owner_username", "url"],
    )


def downgrade():
    op.drop_constraint(
        "uq_repositories_owner_url",
        "repositories",
        type_="unique",
    )
    op.create_unique_constraint(
        "repositories_url_key",
        "repositories",
        ["url"],
    )
