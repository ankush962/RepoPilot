"""add team features

Revision ID: 0005_team_features
Revises: 0004_persistent_conversations
Create Date: 2026-09-01
"""

from alembic import op
import sqlalchemy as sa


revision = "0005_team_features"
down_revision = "0004_persistent_conversations"
branch_labels = None
depends_on = None


def make_unique_slug(
    conn,
    base_slug: str,
) -> str:
    candidate = base_slug
    counter = 2

    while True:
        result = conn.execute(
            sa.text(
                """
                SELECT 1
                FROM workspaces
                WHERE slug = :slug
                LIMIT 1
                """
            ),
            {
                "slug": candidate,
            },
        ).first()

        if not result:
            return candidate

        candidate = f"{base_slug}-{counter}"
        counter += 1


def upgrade() -> None:
    # --------------------------------------------------------------
    # USERS
    # --------------------------------------------------------------

    op.create_table(
        "users",
        sa.Column(
            "id",
            sa.Integer(),
            primary_key=True,
            autoincrement=True,
        ),
        sa.Column(
            "username",
            sa.String(255),
            nullable=False,
        ),
        sa.Column(
            "password_hash",
            sa.String(255),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "username",
            name="uq_users_username",
        ),
    )

    op.create_index(
        "ix_users_username",
        "users",
        ["username"],
        unique=True,
    )

    # --------------------------------------------------------------
    # WORKSPACES
    # --------------------------------------------------------------

    op.create_table(
        "workspaces",
        sa.Column(
            "id",
            sa.Integer(),
            primary_key=True,
            autoincrement=True,
        ),
        sa.Column(
            "name",
            sa.String(255),
            nullable=False,
        ),
        sa.Column(
            "slug",
            sa.String(255),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "slug",
            name="uq_workspaces_slug",
        ),
    )

    op.create_index(
        "ix_workspaces_slug",
        "workspaces",
        ["slug"],
        unique=True,
    )

    # --------------------------------------------------------------
    # WORKSPACE MEMBERSHIPS
    # --------------------------------------------------------------

    op.create_table(
        "workspace_memberships",
        sa.Column(
            "id",
            sa.Integer(),
            primary_key=True,
            autoincrement=True,
        ),
        sa.Column(
            "workspace_id",
            sa.Integer(),
            sa.ForeignKey(
                "workspaces.id",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey(
                "users.id",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column(
            "role",
            sa.String(32),
            nullable=False,
            server_default="viewer",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "user_id",
            name="uq_workspace_user",
        ),
    )

    op.create_index(
        "ix_workspace_memberships_workspace_id",
        "workspace_memberships",
        ["workspace_id"],
    )

    op.create_index(
        "ix_workspace_memberships_user_id",
        "workspace_memberships",
        ["user_id"],
    )

    # --------------------------------------------------------------
    # ADD WORKSPACE TO EXISTING REPOSITORIES
    #
    # IMPORTANT:
    # owner_username is intentionally NOT removed.
    # --------------------------------------------------------------

    op.add_column(
        "repositories",
        sa.Column(
            "workspace_id",
            sa.Integer(),
            nullable=True,
        ),
    )

    op.create_index(
        "ix_repositories_workspace_id",
        "repositories",
        ["workspace_id"],
    )

    op.create_foreign_key(
        "fk_repositories_workspace_id",
        "repositories",
        "workspaces",
        ["workspace_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # --------------------------------------------------------------
    # MIGRATE EXISTING REPOSITORIES
    # --------------------------------------------------------------

    conn = op.get_bind()

    owners = conn.execute(
        sa.text(
            """
            SELECT DISTINCT owner_username
            FROM repositories
            WHERE owner_username IS NOT NULL
              AND TRIM(owner_username) <> ''
            """
        )
    ).fetchall()

    for row in owners:
        username = row[0].strip()

        # ----------------------------------------------------------
        # Create user if it doesn't exist.
        #
        # Existing accounts are migrated without changing their
        # current authentication behavior. The placeholder hash is
        # replaced when the real User authentication system is added.
        # ----------------------------------------------------------

        user = conn.execute(
            sa.text(
                """
                SELECT id
                FROM users
                WHERE username = :username
                LIMIT 1
                """
            ),
            {
                "username": username,
            },
        ).first()

        if user:
            user_id = user[0]
        else:
            user_result = conn.execute(
                sa.text(
                    """
                    INSERT INTO users (
                        username,
                        password_hash
                    )
                    VALUES (
                        :username,
                        :password_hash
                    )
                    RETURNING id
                    """
                ),
                {
                    "username": username,
                    "password_hash": "MIGRATED_PENDING_AUTH",
                },
            )

            user_id = user_result.scalar_one()

        # ----------------------------------------------------------
        # Create one personal workspace for the existing owner.
        # ----------------------------------------------------------

        base_slug = (
            username.lower()
            .strip()
            .replace(" ", "-")
        )

        base_slug = "".join(
            character
            if character.isalnum() or character == "-"
            else "-"
            for character in base_slug
        )

        base_slug = (
            base_slug.strip("-")
            or f"user-{user_id}"
        )

        workspace = conn.execute(
            sa.text(
                """
                SELECT id
                FROM workspaces
                WHERE slug = :slug
                LIMIT 1
                """
            ),
            {
                "slug": base_slug,
            },
        ).first()

        if workspace:
            workspace_id = workspace[0]
        else:
            slug = make_unique_slug(
                conn,
                base_slug,
            )

            workspace_result = conn.execute(
                sa.text(
                    """
                    INSERT INTO workspaces (
                        name,
                        slug
                    )
                    VALUES (
                        :name,
                        :slug
                    )
                    RETURNING id
                    """
                ),
                {
                    "name": f"{username}'s Workspace",
                    "slug": slug,
                },
            )

            workspace_id = (
                workspace_result.scalar_one()
            )

        # ----------------------------------------------------------
        # Make the existing user the workspace owner.
        # ----------------------------------------------------------

        membership = conn.execute(
            sa.text(
                """
                SELECT id
                FROM workspace_memberships
                WHERE workspace_id = :workspace_id
                  AND user_id = :user_id
                LIMIT 1
                """
            ),
            {
                "workspace_id": workspace_id,
                "user_id": user_id,
            },
        ).first()

        if not membership:
            conn.execute(
                sa.text(
                    """
                    INSERT INTO workspace_memberships (
                        workspace_id,
                        user_id,
                        role
                    )
                    VALUES (
                        :workspace_id,
                        :user_id,
                        'owner'
                    )
                    """
                ),
                {
                    "workspace_id": workspace_id,
                    "user_id": user_id,
                },
            )

        # ----------------------------------------------------------
        # Attach all repositories belonging to this owner.
        # ----------------------------------------------------------

        conn.execute(
            sa.text(
                """
                UPDATE repositories
                SET workspace_id = :workspace_id
                WHERE owner_username = :username
                  AND workspace_id IS NULL
                """
            ),
            {
                "workspace_id": workspace_id,
                "username": username,
            },
        )


def downgrade() -> None:
    # Remove repository workspace relationship first.

    op.drop_constraint(
        "fk_repositories_workspace_id",
        "repositories",
        type_="foreignkey",
    )

    op.drop_index(
        "ix_repositories_workspace_id",
        table_name="repositories",
    )

    op.drop_column(
        "repositories",
        "workspace_id",
    )

    op.drop_index(
        "ix_workspace_memberships_user_id",
        table_name="workspace_memberships",
    )

    op.drop_index(
        "ix_workspace_memberships_workspace_id",
        table_name="workspace_memberships",
    )

    op.drop_table(
        "workspace_memberships"
    )

    op.drop_index(
        "ix_workspaces_slug",
        table_name="workspaces",
    )

    op.drop_table(
        "workspaces"
    )

    op.drop_index(
        "ix_users_username",
        table_name="users",
    )

    op.drop_table(
        "users"
    )