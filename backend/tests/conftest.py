from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.database import get_db
from app.main import app
from app.models import (
    AuthSession,
    CodeChunk,
    Conversation,
    ConversationMessage,
    IndexJob,
    Repository,
    User,
    Workspace,
    WorkspaceMembership,
    WorkspaceUsage,
)
from app.services.auth import require_auth


class FakeQuery:
    def __init__(self, db: "FakeDB", *models):
        self.db = db
        self.models = models
        self.model = models[0] if models else None

        if len(models) == 1:
            self._items = list(
                db.storage.get(models[0], [])
            )
        else:
            self._items = []

    def filter(self, *conditions):
        for condition in conditions:
            left = getattr(condition, "left", None)
            right = getattr(condition, "right", None)

            field_name = getattr(left, "name", None)

            if not field_name:
                continue

            expected = getattr(right, "value", right)

            self._items = [
                item
                for item in self._items
                if getattr(item, field_name, None) == expected
            ]

        return self

    def order_by(self, *args):
        return self

    def first(self):
        return (
            self._items[0]
            if self._items
            else None
        )

    def all(self):
        return list(self._items)

    def count(self):
        return len(self._items)

    def subquery(self):
        return self


class FakeDB:
    def __init__(self):
        self.storage = {
            User: [],
            Workspace: [],
            WorkspaceMembership: [],
            Repository: [],
            CodeChunk: [],
            Conversation: [],
            ConversationMessage: [],
            IndexJob: [],
            AuthSession: [],
            WorkspaceUsage: [],
        }

        self.next_ids = {
            User: 1,
            Workspace: 1,
            WorkspaceMembership: 1,
            Repository: 1,
            CodeChunk: 1,
            Conversation: 1,
            ConversationMessage: 1,
            IndexJob: 1,
            AuthSession: 1,
            WorkspaceUsage: 1,
        }

    def add(self, obj):
        model = type(obj)

        if model not in self.storage:
            self.storage[model] = []

        if (
            getattr(obj, "id", None) is None
            and model in self.next_ids
        ):
            obj.id = self.next_ids[model]
            self.next_ids[model] += 1

        self.storage[model].append(obj)

    def add_all(self, objects):
        for obj in objects:
            self.add(obj)

    def query(self, *models):
        return FakeQuery(
            self,
            *models,
        )

    def get(self, model, object_id):
        for item in self.storage.get(model, []):
            if getattr(item, "id", None) == object_id:
                return item

        return None

    def flush(self):
        return None

    def commit(self):
        return None

    def refresh(self, obj):
        return obj

    def rollback(self):
        return None

    def delete(self, obj):
        model = type(obj)

        if (
            model in self.storage
            and obj in self.storage[model]
        ):
            self.storage[model].remove(obj)

    def close(self):
        return None


@pytest.fixture
def fake_db():
    return FakeDB()


@pytest.fixture
def client(fake_db):
    """
    Authenticated/dev-mode application client.

    Most functional tests use the existing development-user behavior
    when AUTH_ENABLED=false.
    """
    app.dependency_overrides = {
        get_db: lambda: fake_db,
        require_auth: lambda: "test-user",
    }

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture
def unauthenticated_client(fake_db, monkeypatch):
    """
    Client used specifically for authentication enforcement tests.

    Temporarily enable authentication and do not override require_auth,
    so protected endpoints must return 401 without a session.
    """
    monkeypatch.setattr(
        settings,
        "auth_enabled",
        True,
    )

    app.dependency_overrides = {
        get_db: lambda: fake_db,
    }

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()