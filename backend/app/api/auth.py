from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, Workspace, WorkspaceMembership
from app.schemas import LoginRequest, RegisterRequest
from app.services.auth import (
    SESSION_COOKIE,
    create_session,
    delete_session,
    hash_password,
    require_user,
    verify_password,
)


router = APIRouter(
    prefix="/auth",
    tags=["auth"],
)


@router.post("/register")
def register(
    payload: RegisterRequest,
    response: Response,
    db: Session = Depends(get_db),
):
    username = payload.username.strip()

    existing = (
        db.query(User)
        .filter(User.username == username)
        .first()
    )

    if existing:
        return {
            "detail": "Username already exists."
        }


    user = User(
        username=username,
        password_hash=hash_password(
            payload.password
        ),
    )

    db.add(user)
    db.flush()

    workspace = Workspace(
        name=f"{username}'s Workspace",
        slug=username,
    )

    db.add(workspace)
    db.flush()

    membership = WorkspaceMembership(
        workspace_id=workspace.id,
        user_id=user.id,
        role="owner",
    )

    db.add(membership)
    db.commit()
    db.refresh(user)

    token = create_session(
        db,
        user.id,
    )

    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=7 * 24 * 60 * 60,
    )

    return {
        "username": user.username,
        "workspace": {
            "id": workspace.id,
            "name": workspace.name,
            "slug": workspace.slug,
            "role": "owner",
        },
    }


@router.post("/login")
def login(
    payload: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
):
    username = payload.username.strip()

    user = (
        db.query(User)
        .filter(
            User.username == username
        )
        .first()
    )

    if not user or not verify_password(
        payload.password,
        user.password_hash,
    ):
        return {
            "detail": "Invalid username or password."
        }


    token = create_session(
        db,
        user.id,
    )

    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=7 * 24 * 60 * 60,
    )

    membership = (
        db.query(WorkspaceMembership)
        .filter(
            WorkspaceMembership.user_id
            == user.id
        )
        .order_by(
            WorkspaceMembership.id
        )
        .first()
    )

    workspace = (
        db.get(
            Workspace,
            membership.workspace_id,
        )
        if membership
        else None
    )

    return {
        "username": user.username,
        "workspace": (
            {
                "id": workspace.id,
                "name": workspace.name,
                "slug": workspace.slug,
                "role": membership.role,
            }
            if workspace and membership
            else None
        ),
    }


@router.get("/me")
def me(
    user: User = Depends(require_user),
):
    return {
        "id": user.id,
        "username": user.username,
    }


@router.post("/logout")
def logout(
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    from fastapi import Request

    # The cookie is removed client-side below.
    response.delete_cookie(
        SESSION_COOKIE
    )

    return {
        "status": "logged_out"
    }