from pathlib import Path

IGNORED_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", "dist", "build"}
ALLOWED_EXTENSIONS = {".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".cpp", ".cc", ".c", ".h", ".hpp", ".go", ".rs", ".rb", ".php", ".html", ".css", ".md", ".json", ".yaml", ".yml"}

def iter_code_files(root: str):
    for path in Path(root).rglob("*"):
        if path.is_file() and not any(p in IGNORED_DIRS for p in path.parts) and path.suffix.lower() in ALLOWED_EXTENSIONS:
            yield path

def chunk_file(path: Path, chunk_lines: int = 80, overlap: int = 10):
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return []
    chunks, start = [], 0
    while start < len(lines):
        end = min(start + chunk_lines, len(lines))
        chunks.append({"start_line": start + 1, "end_line": end, "content": "\n".join(lines[start:end])})
        if end == len(lines): break
        start = end - overlap
    return chunks
