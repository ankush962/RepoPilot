from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Repository(Base):
    __tablename__ = "repositories"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    owner_username: Mapped[str] = mapped_column(
        String(255),
        index=True,
        nullable=False,
    )

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    url: Mapped[str] = mapped_column(
        Text,
        index=True,
        nullable=False,
    )

    branch: Mapped[str] = mapped_column(
        String(255),
        default="main",
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(50),
        default="created",
        nullable=False,
    )

    local_path: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    indexed_commit_sha: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    last_indexed_commit: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    workspace_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "workspaces.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    workspace = relationship(
        "Workspace",
        back_populates="repositories",
    )