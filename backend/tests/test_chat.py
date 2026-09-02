import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Repository
from app.database import get_db
from app.services.auth import require_auth


class FakeDB:
    def get(self, model, repository_id):
        if model is Repository and repository_id == 1:
            return Repository(
                id=1,
                owner_username="test-user",
                name="test-repo",
                url="https://github.com/example/test-repo",
                branch="main",
                status="ready",
            )
        return None


@pytest.fixture
def client():
    app.dependency_overrides[get_db] = lambda: FakeDB()
    app.dependency_overrides[require_auth] = lambda: "test-user"

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()