from __future__ import annotations

import ast
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import ollama

from app.config import settings


MODEL = settings.ollama_model

OLLAMA = ollama.Client(
    host=settings.ollama_url,
    timeout=settings.ollama_timeout_seconds,
)


IGNORED_DIRS = {
    ".git",
    ".next",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "dist",
    "build",
    ".pytest_cache",
}


CODE_EXTENSIONS = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".mjs",
    ".cjs",
}


def _is_code_file(path: Path) -> bool:
    return (
        path.suffix.lower() in CODE_EXTENSIONS
        and not any(
            part in IGNORED_DIRS
            for part in path.parts
        )
    )


def _relative_path(
    root: Path,
    path: Path,
) -> str:
    return path.relative_to(root).as_posix()


def _read_text(
    path: Path,
    max_chars: int = 12000,
) -> str:
    try:
        return path.read_text(
            encoding="utf-8",
            errors="replace",
        )[:max_chars]
    except Exception:
        return ""


def _python_imports(
    content: str,
) -> list[str]:
    imports: list[str] = []

    try:
        tree = ast.parse(content)
    except SyntaxError:
        return imports

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)

        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)

    return imports


def _javascript_imports(
    content: str,
) -> list[str]:
    imports: list[str] = []

    patterns = [
        r'import\s+.*?\s+from\s+[\'"]([^\'"]+)[\'"]',
        r'import\s+[\'"]([^\'"]+)[\'"]',
        r'require\(\s*[\'"]([^\'"]+)[\'"]\s*\)',
        r'export\s+.*?\s+from\s+[\'"]([^\'"]+)[\'"]',
    ]

    for pattern in patterns:
        imports.extend(
            re.findall(
                pattern,
                content,
                flags=re.MULTILINE,
            )
        )

    return imports


def _extract_imports(
    path: Path,
    content: str,
) -> list[str]:
    if path.suffix.lower() == ".py":
        return _python_imports(content)

    return _javascript_imports(content)


def _python_symbols(
    content: str,
) -> dict[str, list[str]]:
    result = {
        "classes": [],
        "functions": [],
        "routes": [],
    }

    try:
        tree = ast.parse(content)
    except SyntaxError:
        return result

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            result["classes"].append(node.name)

        elif isinstance(
            node,
            (
                ast.FunctionDef,
                ast.AsyncFunctionDef,
            ),
        ):
            result["functions"].append(node.name)

            for decorator in node.decorator_list:
                text = ast.unparse(decorator)

                if any(
                    method in text
                    for method in [
                        "get(",
                        "post(",
                        "put(",
                        "patch(",
                        "delete(",
                    ]
                ):
                    result["routes"].append(
                        node.name
                    )

    return result


def _javascript_symbols(
    content: str,
) -> dict[str, list[str]]:
    result = {
        "classes": [],
        "functions": [],
        "routes": [],
    }

    result["functions"] = re.findall(
        r"(?:function|async\s+function)\s+([A-Za-z_$][\w$]*)",
        content,
    )

    result["classes"] = re.findall(
        r"class\s+([A-Za-z_$][\w$]*)",
        content,
    )

    routes = re.findall(
        r"\.(get|post|put|patch|delete)\s*\(",
        content,
    )

    result["routes"] = [
        f"{method.upper()} route"
        for method in routes
    ]

    return result


def _extract_symbols(
    path: Path,
    content: str,
) -> dict[str, list[str]]:
    if path.suffix.lower() == ".py":
        return _python_symbols(content)

    return _javascript_symbols(content)


def _classify_file(
    relative_path: str,
) -> str:
    path = relative_path.lower()

    if (
        path.startswith("frontend/")
        or "/frontend/" in path
    ):
        return "frontend"

    if (
        path.startswith("backend/")
        or "/backend/" in path
    ):
        return "backend"

    if (
        "api/" in path
        or path.endswith("/routes.py")
        or path.endswith("/router.py")
    ):
        return "api"

    if (
        "service" in path
        or "/services/" in path
    ):
        return "service"

    if (
        "model" in path
        or "/models/" in path
        or "schema" in path
    ):
        return "data"

    if (
        "database" in path
        or "migration" in path
        or "alembic" in path
    ):
        return "database"

    if (
        "embedding" in path
        or "vector" in path
        or "agent" in path
        or "llm" in path
    ):
        return "ai"

    if (
        "test" in path
        or path.startswith("tests/")
    ):
        return "tests"

    if path.endswith(
        (
            ".json",
            ".yaml",
            ".yml",
            ".toml",
            ".env",
        )
    ):
        return "config"

    return "other"


def _resolve_python_import(
    root: Path,
    source_path: str,
    imported: str,
) -> str | None:
    if imported.startswith("."):
        return None

    parts = imported.split(".")

    candidates = [
        root / Path(*parts),
        root / Path(*parts).with_suffix(".py"),
        root / Path(*parts) / "__init__.py",
        root / "backend" / Path(*parts),
        root / "backend" / Path(*parts).with_suffix(".py"),
        root / "backend" / Path(*parts) / "__init__.py",
    ]

    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return _relative_path(root, candidate)

    return None


def _resolve_javascript_import(
    root: Path,
    source_path: Path,
    imported: str,
) -> str | None:
    if not imported.startswith("."):
        return None

    base = source_path.parent / imported

    candidates = [
        base,
        Path(f"{base}.js"),
        Path(f"{base}.jsx"),
        Path(f"{base}.ts"),
        Path(f"{base}.tsx"),
        base / "index.js",
        base / "index.jsx",
        base / "index.ts",
        base / "index.tsx",
    ]

    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return _relative_path(root, candidate)

    return None


def analyze_repository(
    local_path: str,
) -> dict[str, Any]:
    root = Path(local_path)

    if not root.exists():
        raise FileNotFoundError(
            f"Repository workspace does not exist: {local_path}"
        )

    code_files: list[Path] = []

    for path in root.rglob("*"):
        if path.is_file() and _is_code_file(path):
            code_files.append(path)

    code_files.sort(
        key=lambda path: _relative_path(root, path)
    )

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    category_counts = Counter()
    dependency_counts = Counter()
    symbol_counts = Counter()

    file_records: dict[str, dict[str, Any]] = {}

    for path in code_files:
        relative_path = _relative_path(
            root,
            path,
        )

        content = _read_text(path)

        category = _classify_file(
            relative_path
        )

        imports = _extract_imports(
            path,
            content,
        )

        symbols = _extract_symbols(
            path,
            content,
        )

        category_counts[category] += 1

        symbol_counts["functions"] += len(
            symbols["functions"]
        )
        symbol_counts["classes"] += len(
            symbols["classes"]
        )
        symbol_counts["routes"] += len(
            symbols["routes"]
        )

        record = {
            "path": relative_path,
            "category": category,
            "imports": imports[:30],
            "functions": symbols["functions"][:30],
            "classes": symbols["classes"][:30],
            "routes": symbols["routes"][:30],
            "lines": len(
                content.splitlines()
            ),
        }

        file_records[
            relative_path
        ] = record

        nodes.append(
            {
                "id": relative_path,
                "label": Path(
                    relative_path
                ).name,
                "category": category,
                "lines": record["lines"],
            }
        )

    file_paths = set(
        file_records.keys()
    )

    for relative_path, record in file_records.items():
        source_path = root / relative_path

        for imported in record["imports"]:
            target_path = None

            if source_path.suffix.lower() == ".py":
                target_path = _resolve_python_import(
                    root,
                    relative_path,
                    imported,
                )
            else:
                target_path = _resolve_javascript_import(
                    root,
                    source_path,
                    imported,
                )

            if (
                target_path
                and target_path in file_paths
                and target_path != relative_path
            ):
                dependency_counts[target_path] += 1

                edges.append(
                    {
                        "source": relative_path,
                        "target": target_path,
                        "type": "imports",
                    }
                )

    important_files = []

    for path, record in file_records.items():
        incoming = dependency_counts[path]

        score = (
            incoming * 3
            + len(record["routes"]) * 3
            + len(record["functions"])
            + len(record["classes"])
        )

        important_files.append(
            {
                "path": path,
                "category": record["category"],
                "score": score,
                "incoming_dependencies": incoming,
                "functions": len(
                    record["functions"]
                ),
                "classes": len(
                    record["classes"]
                ),
                "routes": len(
                    record["routes"]
                ),
            }
        )

    important_files.sort(
        key=lambda item: (
            item["score"],
            item["incoming_dependencies"],
        ),
        reverse=True,
    )

    architecture_summary = {
        "total_code_files": len(
            code_files
        ),
        "categories": dict(
            category_counts
        ),
        "symbols": dict(
            symbol_counts
        ),
        "graph": {
            "nodes": nodes,
            "edges": edges,
        },
        "important_files": important_files[
            :20
        ],
        "files": list(
            file_records.values()
        ),
    }

    return architecture_summary


def build_architecture_context(
    analysis: dict[str, Any],
) -> str:
    parts = []

    parts.append(
        "REPOSITORY STATISTICS:\n"
        + json.dumps(
            {
                "total_code_files": analysis[
                    "total_code_files"
                ],
                "categories": analysis[
                    "categories"
                ],
                "symbols": analysis[
                    "symbols"
                ],
            },
            indent=2,
        )
    )

    parts.append(
        "\nIMPORTANT FILES:\n"
        + json.dumps(
            analysis[
                "important_files"
            ],
            indent=2,
        )
    )

    parts.append(
        "\nDEPENDENCY GRAPH:\n"
        + json.dumps(
            analysis["graph"],
            indent=2,
        )
    )

    parts.append(
        "\nMODULE DETAILS:\n"
        + json.dumps(
            analysis["files"][:80],
            indent=2,
        )
    )

    return "\n\n".join(parts)


ARCHITECTURE_SYSTEM_PROMPT = """
You are RepoPilot Architecture Intelligence.

Analyze ONLY the supplied repository architecture evidence.

Do not invent components, relationships, services, or technologies.

Your response must be useful to a software engineer.

Explain:

1. High-level architecture
2. Major components
3. Frontend
4. Backend
5. APIs
6. Services
7. Database/data layer
8. AI/LLM/embeddings/retrieval
9. Repository ingestion/indexing
10. Important modules
11. Request/data flow
12. Dependencies and relationships
13. Potential architectural risks

When evidence supports it, mention exact file paths.

Clearly distinguish directly observed architecture from reasonable
structural inference.

Do not claim that something exists unless the evidence supports it.
"""


def generate_architecture_explanation(
    analysis: dict[str, Any],
) -> str:
    context = build_architecture_context(
        analysis
    )

    prompt = f"""
Generate an architecture overview for this repository.

ARCHITECTURE EVIDENCE:

{context}

Produce:

## Architecture overview

## Major components

## Request flow

## Important modules

## Dependency relationships

## Architectural observations

## Potential risks

Keep the explanation concrete and tied to the supplied evidence.
"""

    response = OLLAMA.chat(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": ARCHITECTURE_SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        options={
            "temperature": 0.0,
            "num_predict": 2500,
            "num_ctx": 12000,
        },
    )

    return (
        response["message"]["content"]
        .strip()
    )


def architecture_report(
    local_path: str,
) -> dict[str, Any]:
    analysis = analyze_repository(
        local_path
    )

    try:
        explanation = generate_architecture_explanation(
            analysis
        )
    except Exception as exc:
        explanation = (
            "Unable to generate the AI architecture explanation: "
            f"{exc}"
        )

    return {
        "summary": explanation,
        "statistics": {
            "total_code_files": analysis[
                "total_code_files"
            ],
            "categories": analysis[
                "categories"
            ],
            "symbols": analysis[
                "symbols"
            ],
        },
        "important_files": analysis[
            "important_files"
        ],
        "graph": analysis["graph"],
        "modules": analysis["files"],
    }
