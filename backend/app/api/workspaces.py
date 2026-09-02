from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    User,
    Workspace,
    WorkspaceMembership,
)
from app.services.auth import require_user
from app.services.workspaces import (
    get_membership,
    require_permission,
)


router = APIRouter(
    prefix="/workspaces",
    tags=["workspaces"],
)


@router.get("")
def list_workspaces(
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    memberships = (
        db.query(WorkspaceMembership)
        .filter(
            WorkspaceMembership.user_id
            == user.id
        )
        .order_by(
            WorkspaceMembership.id
        )
        .all()
    )

    result = []

    for membership in memberships:
        workspace = db.get(
            Workspace,
            membership.workspace_id,
        )

        if not workspace:
            continue

        result.append(
            {
                "id": workspace.id,
                "name": workspace.name,
                "slug": workspace.slug,
                "role": membership.role,
                "created_at": workspace.created_at,
            }
        )

    return result


@router.get("/{workspace_id}")
def get_workspace(
    workspace_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    membership = get_membership(
        db,
        workspace_id,
        user.id,
    )

    workspace = db.get(
        Workspace,
        workspace_id,
    )

    if not workspace:
        raise HTTPException(
            status_code=404,
            detail="Workspace not found.",
        )

    return {
        "id": workspace.id,
        "name": workspace.name,
        "slug": workspace.slug,
        "role": membership.role,
        "created_at": workspace.created_at,
    }


@router.post("")
def create_workspace(
    payload: dict,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    name = str(
        payload.get(
            "name",
            "",
        )
    ).strip()

    if not name:
        raise HTTPException(
            status_code=400,
            detail="Workspace name is required.",
        )

    slug = (
        name.lower()
        .replace(" ", "-")
    )

    existing = (
        db.query(Workspace)
        .filter(
            Workspace.slug == slug
        )
        .first()
    )

    if existing:
        raise HTTPException(
            status_code=409,
            detail="Workspace slug already exists.",
        )

    workspace = Workspace(
        name=name,
        slug=slug,
    )

    db.add(workspace)
    db.flush()

    db.add(
        WorkspaceMembership(
            workspace_id=workspace.id,
            user_id=user.id,
            role="owner",
        )
    )

    db.commit()
    db.refresh(workspace)

    return {
        "id": workspace.id,
        "name": workspace.name,
        "slug": workspace.slug,
        "role": "owner",
    }
@router.get("/{workspace_id}/members")
def list_members(
    workspace_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    get_membership(
        db,
        workspace_id,
        user.id,
    )

    rows = (
        db.query(
            User,
            WorkspaceMembership,
        )
        .join(
            WorkspaceMembership,
            WorkspaceMembership.user_id
            == User.id,
        )
        .filter(
            WorkspaceMembership.workspace_id
            == workspace_id
        )
        .all()
    )

    return [
        {
            "user_id": member.id,
            "username": member.username,
            "role": membership.role,
            "created_at": membership.created_at,
        }
        for member, membership in rows
    ]


@router.post("/{workspace_id}/members")
def add_member(
    workspace_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    require_permission(
        db,
        workspace_id,
        user,
        "manage_members",
    )

    username = str(
        payload.get(
            "username",
            "",
        )
    ).strip()

    role = str(
        payload.get(
            "role",
            "member",
        )
    ).strip()

    if role not in {
        "admin",
        "member",
        "viewer",
    }:
        raise HTTPException(
            status_code=400,
            detail="Invalid role.",
        )

    target = (
        db.query(User)
        .filter(
            User.username == username
        )
        .first()
    )

    if not target:
        raise HTTPException(
            status_code=404,
            detail="User not found.",
        )

    existing = (
        db.query(WorkspaceMembership)
        .filter(
            WorkspaceMembership.workspace_id
            == workspace_id,
            WorkspaceMembership.user_id
            == target.id,
        )
        .first()
    )

    if existing:
        raise HTTPException(
            status_code=409,
            detail="User is already a workspace member.",
        )

    membership = WorkspaceMembership(
        workspace_id=workspace_id,
        user_id=target.id,
        role=role,
    )

    db.add(membership)
    db.commit()
    db.refresh(membership)

    return {
        "user_id": target.id,
        "username": target.username,
        "role": membership.role,
    }


@router.patch("/{workspace_id}/members/{user_id}")
def update_member_role(
    workspace_id: int,
    user_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    require_permission(
        db,
        workspace_id,
        user,
        "manage_members",
    )

    new_role = str(
        payload.get(
            "role",
            "",
        )
    ).strip()

    if new_role not in {
        "admin",
        "member",
        "viewer",
    }:
        raise HTTPException(
            status_code=400,
            detail="Invalid role.",
        )

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
            status_code=404,
            detail="Membership not found.",
        )

    if membership.role == "owner":
        raise HTTPException(
            status_code=400,
            detail="The workspace owner cannot be demoted.",
        )

    membership.role = new_role
    db.commit()

    return {
        "user_id": user_id,
        "role": new_role,
    }


@router.delete("/{workspace_id}/members/{user_id}")
def remove_member(
    workspace_id: int,
    user_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    require_permission(
        db,
        workspace_id,
        user,
        "manage_members",
    )

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
            status_code=404,
            detail="Membership not found.",
        )

    if membership.role == "owner":
        raise HTTPException(
            status_code=400,
            detail="The workspace owner cannot be removed.",
        )

    db.delete(membership)
    db.commit()

    return {
        "status": "removed"
    }