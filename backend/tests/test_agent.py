from app.services.agent import classify_question


def test_classify_bug_question():
    assert classify_question("What bugs are in this code?") == "bug"


def test_classify_architecture_question():
    assert classify_question("Explain the architecture") == "architecture"


def test_classify_explanation_question():
    assert classify_question("How does this work?") == "explanation"


def test_classify_fix_question():
    assert classify_question("How can I improve this?") == "fix"


def test_classify_general_question():
    assert classify_question("hello") == "general"