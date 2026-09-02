
from __future__ import annotations

import pytest

from fastapi.testclient import TestClient

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
    def __init__(self, db: "FakeDB", model):
        self.db = db
        self.model = model
        self._items = list(db.storage.get(model, []))

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
        return self._items[0] if self._items else None

    def all(self):
        return list(self._items)

    def count(self):
        return len(self._items)


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

    def query(self, model):
        return FakeQuery(self, model)

    def get(self, model, object_id):
        for item in self.storage.get(model, []):
            if getattr(item, "id", None) == object_id:
                return item

        if model is Repository and object_id == 1:
            return Repository(
                id=1,
                owner_username="test-user",
                name="test-repo",
                url="https://github.com/example/test-repo",
                branch="main",
                status="ready",
            )

        return None

    def flush(self):
        return None

    def commit(self):
        return None

    def refresh(self, obj):
        return obj

    def delete(self, obj):
        model = type(obj)

        if (
            model in self.storage
            and obj in self.storage[model]
        ):
            self.storage[model].remove(obj)


@pytest.fixture
def fake_db():
    return FakeDB()


@pytest.fixture
def client(fake_db):
    app.dependency_overrides = {
        get_db: lambda: fake_db,
        require_auth: lambda: "test-user",
    }

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
