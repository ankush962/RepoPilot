from app.services.auth import create_access_token


def test_token_is_created():
    token = create_access_token("test-user")
    assert isinstance(token, str)
    assert token
