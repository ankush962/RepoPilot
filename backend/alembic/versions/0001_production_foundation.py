"""
production foundation

Revision ID: 0001_production_foundation
Revises:
"""
from pgvector.sqlalchemy import Vector
from alembic import op
import sqlalchemy as sa


revision = "0001_production_foundation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # --------------------------------------------------------------
    # PGVECTOR
    # --------------------------------------------------------------

    op.execute(
        "CREATE EXTENSION IF NOT EXISTS vector"
    )

    # --------------------------------------------------------------
    # REPOSITORIES
    #
    # This represents the original repository table.
    # Ownership/workspace fields are added by later migrations.
    # --------------------------------------------------------------

    op.create_table(
        "repositories",
        sa.Column(
            "id",
            sa.Integer(),
            primary_key=True,
            autoincrement=True,
        ),
        sa.Column(
            "name",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "url",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "branch",
            sa.String(length=255),
            nullable=False,
            server_default="main",
        ),
        sa.Column(
            "status",
            sa.String(length=50),
            nullable=False,
            server_default="created",
        ),
        sa.Column(
            "local_path",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "indexed_commit_sha",
            sa.String(length=64),
            nullable=True,
        ),
        sa.Column(
            "last_indexed_commit",
            sa.String(length=64),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint(
            "url",
            name="repositories_url_key",
        ),
    )

    # The old application schema had a URL index as well as the
    # uniqueness constraint. Migration 0003 explicitly removes it.
    op.create_index(
        "ix_repositories_url",
        "repositories",
        ["url"],
    )

    # --------------------------------------------------------------
    # CODE CHUNKS
    #
    # content_hash and chunk_type are added by this migration below,
    # because they were introduced after the original MVP schema.
    # --------------------------------------------------------------

    op.create_table(
        "code_chunks",
        sa.Column(
            "id",
            sa.Integer(),
            primary_key=True,
            autoincrement=True,
        ),
        sa.Column(
            "repository_id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "file_path",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "start_line",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "end_line",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "content",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "embedding",
            Vector(768),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["repository_id"],
            ["repositories.id"],
            name="fk_code_chunks_repository_id",
            ondelete="CASCADE",
        ),
    )

    op.create_index(
        "ix_code_chunks_repository_id",
        "code_chunks",
        ["repository_id"],
    )

    # --------------------------------------------------------------
    # INDEXING JOBS
    # --------------------------------------------------------------

    op.create_table(
        "index_jobs",
        sa.Column(
            "id",
            sa.Integer(),
            primary_key=True,
            autoincrement=True,
        ),
        sa.Column(
            "repository_id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="queued",
        ),
        sa.Column(
            "progress",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "stage",
            sa.String(length=255),
            nullable=False,
            server_default="Queued",
        ),
        sa.Column(
            "attempts",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "error",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "result_chunks",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "result_vectors",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "started_at",
            sa.DateTime(),
            nullable=True,
        ),
        sa.Column(
            "finished_at",
            sa.DateTime(),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["repository_id"],
            ["repositories.id"],
            name="fk_index_jobs_repository_id",
            ondelete="CASCADE",
        ),
    )

    op.create_index(
        "ix_index_jobs_status_created",
        "index_jobs",
        ["status", "created_at"],
    )

    # --------------------------------------------------------------
    # NEW CHUNK METADATA
    # --------------------------------------------------------------

    op.add_column(
        "code_chunks",
        sa.Column(
            "content_hash",
            sa.String(length=64),
            nullable=True,
        ),
    )

    op.add_column(
        "code_chunks",
        sa.Column(
            "chunk_type",
            sa.String(length=32),
            nullable=True,
            server_default="text",
        ),
    )

    op.create_index(
        "ix_code_chunks_repo_hash",
        "code_chunks",
        ["repository_id", "content_hash"],
    )


def downgrade():
    # Remove indexes first.
    op.drop_index(
        "ix_code_chunks_repo_hash",
        table_name="code_chunks",
    )

    op.drop_index(
        "ix_index_jobs_status_created",
        table_name="index_jobs",
    )

    op.drop_index(
        "ix_code_chunks_repository_id",
        table_name="code_chunks",
    )

    op.drop_index(
        "ix_repositories_url",
        table_name="repositories",
    )

    # Drop dependent tables first.
    op.drop_table("index_jobs")
    op.drop_table("code_chunks")
    op.drop_table("repositories")