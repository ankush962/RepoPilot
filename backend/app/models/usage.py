from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class WorkspaceUsage(Base):
    __tablename__ = "workspace_usage"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        index=True,
    )

    period_start: Mapped[date] = mapped_column(
        Date,
    )

    ai_questions: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )

    index_jobs: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )