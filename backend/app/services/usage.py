from datetime import date

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import (
    Workspace,
    WorkspaceUsage,
)


LIMITS = {
    "members": 5,
    "repositories": 10,
    "ai_questions": 500,
    "index_jobs": 100,
}


def current_period() -> date:
    today = date.today()

    return date(
        today.year,
        today.month,
        1,
    )


def get_usage(
    db: Session,
    workspace_id: int,
):
    period = current_period()

    usage = (
        db.query(WorkspaceUsage)
        .filter(
            WorkspaceUsage.workspace_id
            == workspace_id,
            WorkspaceUsage.period_start
            == period,
        )
        .first()
    )

    if not usage:
        usage = WorkspaceUsage(
            workspace_id=workspace_id,
            period_start=period,
        )

        db.add(usage)
        db.commit()
        db.refresh(usage)

    return usage


def check_limit(
    db: Session,
    workspace_id: int,
    key: str,
):
    usage = get_usage(
        db,
        workspace_id,
    )

    current = getattr(
        usage,
        key,
        0,
    )

    limit = LIMITS[key]

    if current >= limit:
        raise HTTPException(
            status_code=429,
            detail=(
                f"Workspace {key} limit reached."
            ),
        )

    return usage


def increment_usage(
    db: Session,
    workspace_id: int,
    key: str,
):
    usage = get_usage(
        db,
        workspace_id,
    )

    setattr(
        usage,
        key,
        getattr(usage, key, 0) + 1,
    )

    db.commit()