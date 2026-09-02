from __future__ import annotations


def test_register_creates_user_and_workspace(client):
    response = client.post(
        "/auth/register",
        json={
            "username": "teamuser",
            "password": "password123",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["username"] == "teamuser"


def test_me_requires_auth(unauthenticated_client):
    response = unauthenticated_client.get(
        "/auth/me"
    )

    assert response.status_code == 401


def test_workspace_list_requires_auth(
    unauthenticated_client,
):
    response = unauthenticated_client.get(
        "/workspaces"
    )

    assert response.status_code == 401


def test_workspace_members_requires_auth(
    unauthenticated_client,
):
    response = unauthenticated_client.get(
        "/workspaces/1/members"
    )

    assert response.status_code == 401


def test_repository_access_requires_auth(
    unauthenticated_client,
):
    response = unauthenticated_client.get(
        "/repositories/4"
    )

    assert response.status_code == 401