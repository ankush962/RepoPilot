from pathlib import Path
import ast
import hashlib

IGNORED_DIRS = {
    ".git", ".venv", "venv", "node_modules", "__pycache__",
    "dist", "build", ".next", "coverage", ".pytest_cache",
}
ALLOWED_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".cpp", ".cc",
    ".c", ".h", ".hpp", ".go", ".rs", ".rb", ".php", ".html",
    ".css", ".md", ".json", ".yaml", ".yml",
}


def iter_code_files(root: str):
    for path in Path(root).rglob("*"):
        if (
            path.is_file()
            and not any(part in IGNORED_DIRS for part in path.parts)
            and path.suffix.lower() in ALLOWED_EXTENSIONS
        ):
            yield path


def _hash(path: Path, start: int, end: int, content: str) -> str:
    payload = f"{path.as_posix()}\0{start}\0{end}\0{content}".encode("utf-8", "ignore")
    return hashlib.sha256(payload).hexdigest()


def _python_chunks(path: Path, lines: list[str]):
    try:
        tree = ast.parse("\n".join(lines))
    except SyntaxError:
        return []

    nodes = [
        node for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        and getattr(node, "lineno", None)
    ]
    nodes.sort(key=lambda n: (n.lineno, getattr(n, "end_lineno", n.lineno)))
    chunks = []
    for node in nodes:
        start = max(1, node.lineno)
        end = min(len(lines), getattr(node, "end_lineno", start))
        content = "\n".join(lines[start - 1:end]).strip()
        if content:
            chunks.append({
                "start_line": start,
                "end_line": end,
                "content": content,
                "chunk_type": "symbol",
                "content_hash": _hash(path, start, end, content),
            })
    return chunks


def chunk_file(path: Path, chunk_lines: int = 80, overlap: int = 10):
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return []

    if not lines:
        return []

    # Python gets symbol-aware chunks first; the fallback captures imports,
    # module-level code, and very large files without losing coverage.
    if path.suffix.lower() == ".py":
        symbols = _python_chunks(path, lines)
        covered = set()
        for item in symbols:
            covered.update(range(item["start_line"], item["end_line"] + 1))
        if symbols and len(covered) >= max(1, int(len(lines) * 0.35)):
            chunks = list(symbols)
            for start in range(0, len(lines), chunk_lines - overlap):
                end = min(start + chunk_lines, len(lines))
                if end - start <= 0:
                    continue
                if any(i + 1 not in covered for i in range(start, end)):
                    content = "\n".join(lines[start:end]).strip()
                    if content:
                        chunks.append({
                            "start_line": start + 1,
                            "end_line": end,
                            "content": content,
                            "chunk_type": "module",
                            "content_hash": _hash(path, start + 1, end, content),
                        })
                if end == len(lines):
                    break
            return _dedupe(chunks)

    chunks = []
    start = 0
    while start < len(lines):
        end = min(start + chunk_lines, len(lines))
        content = "\n".join(lines[start:end]).strip()
        if content:
            chunks.append({
                "start_line": start + 1,
                "end_line": end,
                "content": content,
                "chunk_type": "text",
                "content_hash": _hash(path, start + 1, end, content),
            })
        if end == len(lines):
            break
        start = end - overlap
    return chunks


def _dedupe(chunks):
    seen = set()
    result = []
    for chunk in sorted(chunks, key=lambda x: (x["start_line"], x["end_line"], x["chunk_type"])):
        if chunk["content_hash"] not in seen:
            seen.add(chunk["content_hash"])
            result.append(chunk)
    return result
