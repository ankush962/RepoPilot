from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta
from app.models import (
    AuthSession,
    User,
    Workspace,
    WorkspaceMembership,
)
from fastapi import Cookie, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import AuthSession, User


SESSION_COOKIE = "repopilot_session"
SESSION_DAYS = 7


# ------------------------------------------------------------------
# PASSWORDS
# ------------------------------------------------------------------

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)

    derived = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode(),
        salt,
        240_000,
    )

    return (
        "pbkdf2_sha256$240000$"
        f"{salt.hex()}$"
        f"{derived.hex()}"
    )


def verify_password(
    password: str,
    stored: str,
) -> bool:
    try:
        algorithm, iterations, salt_hex, hash_hex = (
            stored.split("$")
        )

        if algorithm != "pbkdf2_sha256":
            return False

        actual = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode(),
            bytes.fromhex(salt_hex),
            int(iterations),
        )

        return hmac.compare_digest(
            actual,
            bytes.fromhex(hash_hex),
        )

    except Exception:
        return False


# ------------------------------------------------------------------
# COMPATIBILITY TOKEN
# ------------------------------------------------------------------

def create_access_token(username: str) -> str:
    """
    Compatibility token helper used by authentication tests.

    The application authenticates requests with server-side
    session cookies. This helper exists for token-generation
    compatibility and does not replace session authentication.
    """
    if not username or not username.strip():
        raise ValueError(
            "Username is required."
        )

    now = datetime.utcnow()
    expires = now + timedelta(
        days=SESSION_DAYS
    )

    header = {
        "alg": "none",
        "typ": "JWT",
    }

    payload = {
        "sub": username.strip(),
        "iat": int(now.timestamp()),
        "exp": int(expires.timestamp()),
    }

    def encode_part(value: dict) -> str:
        raw = json.dumps(
            value,
            separators=(",", ":"),
        ).encode()

        return (
            base64.urlsafe_b64encode(raw)
            .rstrip(b"=")
            .decode()
        )

    return (
        f"{encode_part(header)}."
        f"{encode_part(payload)}."
        "compat"
    )


# ------------------------------------------------------------------
# SESSIONS
# ------------------------------------------------------------------

def hash_session_token(token: str) -> str:
    return hashlib.sha256(
        token.encode()
    ).hexdigest()


def create_session(
    db: Session,
    user_id: int,
) -> str:
    token = secrets.token_urlsafe(48)

    db.add(
        AuthSession(
            user_id=user_id,
            token_hash=hash_session_token(
                token
            ),
            expires_at=(
                datetime.utcnow()
                + timedelta(days=SESSION_DAYS)
            ),
        )
    )

    db.commit()

    return token


def delete_session(
    db: Session,
    token: str | None,
) -> None:
    if not token:
        return

    session = (
        db.query(AuthSession)
        .filter(
            AuthSession.token_hash
            == hash_session_token(token)
        )
        .first()
    )

    if session:
        db.delete(session)
        db.commit()


# ------------------------------------------------------------------
# DEVELOPMENT USER
# ------------------------------------------------------------------

def get_or_create_dev_user(
    db: Session,
) -> User:
    """
    Return the configured development user and ensure the user has
    an owner workspace.

    Used only when AUTH_ENABLED=false.
    """
    username = (
        settings.auth_username.strip()
        if settings.auth_username
        else "admin"
    )

    # --------------------------------------------------------------
    # USER
    # --------------------------------------------------------------

    user = (
        db.query(User)
        .filter(
            User.username == username
        )
        .first()
    )

    if not user:
        random_password = secrets.token_urlsafe(32)

        user = User(
            username=username,
            password_hash=hash_password(
                random_password
            ),
        )

        db.add(user)
        db.flush()

    # --------------------------------------------------------------
    # WORKSPACE
    # --------------------------------------------------------------

    membership = (
        db.query(WorkspaceMembership)
        .filter(
            WorkspaceMembership.user_id == user.id
        )
        .first()
    )

    if not membership:
        workspace_slug = username.lower().strip()

        workspace = (
            db.query(Workspace)
            .filter(
                Workspace.slug == workspace_slug
            )
            .first()
        )

        if not workspace:
            workspace = Workspace(
                name=f"{username}'s Workspace",
                slug=workspace_slug,
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

    return user
# ------------------------------------------------------------------
# CURRENT USER
# ------------------------------------------------------------------

def get_current_user(
    db: Session,
    token: str | None,
) -> User:
    if not token:
        raise HTTPException(
            status_code=401,
            detail="Authentication required.",
        )

    session = (
        db.query(AuthSession)
        .filter(
            AuthSession.token_hash
            == hash_session_token(token)
        )
        .first()
    )

    if not session:
        raise HTTPException(
            status_code=401,
            detail="Invalid session.",
        )

    if session.expires_at <= datetime.utcnow():
        db.delete(session)
        db.commit()

        raise HTTPException(
            status_code=401,
            detail="Session expired.",
        )

    user = db.get(
        User,
        session.user_id,
    )

    if not user:
        raise HTTPException(
            status_code=401,
            detail="User not found.",
        )

    return user


# ------------------------------------------------------------------
# FASTAPI AUTH DEPENDENCIES
# ------------------------------------------------------------------

def require_user(
    db: Session = Depends(get_db),
    session_token: str | None = Cookie(
        default=None,
        alias=SESSION_COOKIE,
    ),
) -> User:
    """
    Resolve the current application user.

    AUTH_ENABLED=false:
        Automatically use/create the development user.

    AUTH_ENABLED=true:
        Require a valid session cookie.
    """
    if not settings.auth_enabled:
        return get_or_create_dev_user(db)

    return get_current_user(
        db,
        session_token,
    )


def require_auth(
    user: User = Depends(require_user),
) -> str:
    return user.username
