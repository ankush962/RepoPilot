"""
repair legacy conversation message relationship

Revision ID: 0e15e254417d
Revises: 0005_team_features
"""

from alembic import op
import sqlalchemy as sa


revision = "0e15e254417d"
down_revision = "0005_team_features"
branch_labels = None
depends_on = None


def _columns(bind, table_name):
    inspector = sa.inspect(bind)
    return {
        column["name"]
        for column in inspector.get_columns(table_name)
    }


def _foreign_keys(bind, table_name):
    inspector = sa.inspect(bind)
    return inspector.get_foreign_keys(table_name)


def upgrade():
    bind = op.get_bind()

    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    # Fresh installs created by migration 0004 already have the
    # correct conversation_id relationship. Nothing to repair.
    if "conversation_messages" not in tables:
        return

    columns = _columns(
        bind,
        "conversation_messages",
    )

    # --------------------------------------------------------------
    # LEGACY SCHEMA REPAIR
    #
    # Older databases incorrectly used repository_id instead of
    # conversation_id.
    # --------------------------------------------------------------

    if (
        "repository_id" in columns
        and "conversation_id" not in columns
    ):
        # Remove any legacy foreign keys involving repository_id.
        for fk in _foreign_keys(
            bind,
            "conversation_messages",
        ):
            constrained_columns = set(
                fk.get("constrained_columns") or []
            )

            if (
                "repository_id"
                in constrained_columns
                and fk.get("name")
            ):
                op.drop_constraint(
                    fk["name"],
                    "conversation_messages",
                    type_="foreignkey",
                )

        op.drop_column(
            "conversation_messages",
            "repository_id",
        )

        op.add_column(
            "conversation_messages",
            sa.Column(
                "conversation_id",
                sa.Integer(),
                nullable=True,
            ),
        )


def downgrade():
    # This is a repair migration. Do not destroy valid conversation
    # data during downgrade.
    pass
