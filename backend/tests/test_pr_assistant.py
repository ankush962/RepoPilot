from app.services.pr_assistant import _is_test_file


def test_is_test_file_for_python_test():
    assert _is_test_file(
        "backend/tests/test_chat.py"
    )


def test_is_test_file_for_javascript_spec():
    assert _is_test_file(
        "frontend/components/button.spec.tsx"
    )


def test_is_test_file_for_normal_source():
    assert not _is_test_file(
        "backend/app/services/agent.py"
    )