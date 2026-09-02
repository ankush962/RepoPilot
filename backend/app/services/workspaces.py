from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import (
    Repository,
    Workspace,
    WorkspaceMembership,
    User,
)


ROLES = {
    "owner",
    "admin",
    "member",
    "viewer",
}


ROLE_PERMISSIONS = {
    "owner": {
        "manage_workspace",
        "manage_members",
        "add_repository",
        "index_repository",
        "ask_ai",
        "view",
    },
    "admin": {
        "manage_workspace",
        "manage_members",
        "add_repository",
        "index_repository",
        "ask_ai",
        "view",
    },
    "member": {
        "add_repository",
        "index_repository",
        "ask_ai",
        "view",
    },
    "viewer": {
        "ask_ai",
        "view",
    },
}


def get_membership(
    db: Session,
    workspace_id: int,
    user_id: int,
):
    membership = (
        db.query(WorkspaceMembership)
        .filter(
            WorkspaceMembership.workspace_id
            == workspace_id,
            WorkspaceMembership.user_id
            == user_id,
        )
        .first()
    )

    if not membership:
        raise HTTPException(
            status_code=403,
            detail="You are not a member of this workspace.",
        )

    return membership


def require_permission(
    db: Session,
    workspace_id: int,
    user: User,
    permission: str,
):
    membership = get_membership(
        db,
        workspace_id,
        user.id,
    )

    allowed = ROLE_PERMISSIONS.get(
        membership.role,
        set(),
    )

    if permission not in allowed:
        raise HTTPException(
            status_code=403,
            detail="You do not have permission for this action.",
        )

    return membership


def get_repository_for_user(
    db: Session,
    repository_id: int,
    user: User,
):
    repo = db.get(
        Repository,
        repository_id,
    )

    if not repo:
        raise HTTPException(
            status_code=404,
            detail="Repository not found.",
        )

    if repo.workspace_id is not None:
        get_membership(
            db,
            repo.workspace_id,
            user.id,
        )
        return repo

    if repo.owner_username == user.username:
        return repo

    raise HTTPException(
        status_code=404,
        detail="Repository not found.",
    )