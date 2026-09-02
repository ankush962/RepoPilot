from pathlib import Path
from app.services.chunker import chunk_file


def test_python_chunker_is_symbol_aware(tmp_path):
    path = Path(tmp_path) / "sample.py"
    path.write_text(
        "import os\n\n"
        "def hello(name):\n"
        "    return name\n\n"
        "class Demo:\n"
        "    def run(self):\n"
        "        return True\n"
    )
    chunks = chunk_file(path)
    assert chunks
    assert any(chunk["chunk_type"] == "symbol" for chunk in chunks)
    assert all(chunk["content_hash"] for chunk in chunks)
