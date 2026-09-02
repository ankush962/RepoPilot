"""
finalize conversation message relationship

Revision ID: 4e3c38efb450
Revises: 0e15e254417d
"""

from alembic import op
import sqlalchemy as sa


revision = "4e3c38efb450"
down_revision = "0e15e254417d"
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


def _indexes(bind, table_name):
    inspector = sa.inspect(bind)
    return {
        index["name"]
        for index in inspector.get_indexes(table_name)
        if index.get("name")
    }


def upgrade():
    bind = op.get_bind()

    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "conversation_messages" not in tables:
        return

    columns = _columns(
        bind,
        "conversation_messages",
    )

    # --------------------------------------------------------------
    # ENSURE CONVERSATION_ID EXISTS
    # --------------------------------------------------------------

    if "conversation_id" not in columns:
        # Extremely old/malformed installations may still have
        # repository_id at this point.
        if "repository_id" in columns:
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

        columns.add("conversation_id")

    # --------------------------------------------------------------
    # REMOVE LEGACY repository_id IF STILL PRESENT
    # --------------------------------------------------------------

    if "repository_id" in columns:
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

    # --------------------------------------------------------------
    # ENSURE conversation_id FOREIGN KEY
    # --------------------------------------------------------------

    has_conversation_fk = False

    for fk in _foreign_keys(
        bind,
        "conversation_messages",
    ):
        constrained_columns = fk.get(
            "constrained_columns"
        ) or []

        referred_table = fk.get(
            "referred_table"
        )

        if (
            constrained_columns == ["conversation_id"]
            and referred_table == "conversations"
        ):
            has_conversation_fk = True
            break

    if not has_conversation_fk:
        op.create_foreign_key(
            "fk_conversation_messages_conversation_id",
            "conversation_messages",
            "conversations",
            ["conversation_id"],
            ["id"],
            ondelete="CASCADE",
        )

    # --------------------------------------------------------------
    # FINAL NULLABILITY
    # --------------------------------------------------------------
    #
    # Fresh installations have no rows, so this is safe.
    # Existing legacy installations are only made non-null when
    # there are no NULL conversation IDs.
    # --------------------------------------------------------------

    null_count = bind.execute(
        sa.text(
            """
            SELECT COUNT(*)
            FROM conversation_messages
            WHERE conversation_id IS NULL
            """
        )
    ).scalar() or 0

    if null_count == 0:
        op.alter_column(
            "conversation_messages",
            "conversation_id",
            existing_type=sa.Integer(),
            nullable=False,
        )

    # --------------------------------------------------------------
    # INDEXES
    # --------------------------------------------------------------

    indexes = _indexes(
        bind,
        "conversation_messages",
    )

    if (
        "ix_conversation_messages_conversation_id"
        not in indexes
    ):
        op.create_index(
            "ix_conversation_messages_conversation_id",
            "conversation_messages",
            ["conversation_id"],
        )

    if (
        "ix_conversation_messages_created_at"
        not in indexes
    ):
        op.create_index(
            "ix_conversation_messages_created_at",
            "conversation_messages",
            ["created_at"],
        )


def downgrade():
    # Repair migration; intentionally non-destructive.
    pass
