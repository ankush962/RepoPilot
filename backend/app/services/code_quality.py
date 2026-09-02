from __future__ import annotations

import ast
import hashlib
import re
from collections import defaultdict
from pathlib import Path
from typing import Any


SUPPORTED_EXTENSIONS = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
}

IGNORED_PARTS = {
    ".git",
    ".next",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "dist",
    "build",
}


def iter_source_files(root: str):
    base = Path(root)

    if not base.exists():
        return

    for path in base.rglob("*"):
        if not path.is_file():
            continue

        if any(part in IGNORED_PARTS for part in path.parts):
            continue

        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue

        yield path


def relative_path(root: str, path: Path) -> str:
    return path.relative_to(Path(root)).as_posix()


def read_text(path: Path) -> str:
    try:
        return path.read_text(
            encoding="utf-8",
            errors="replace",
        )
    except Exception:
        return ""


def node_line(node: ast.AST) -> int:
    return int(getattr(node, "lineno", 1))


def add_finding(
    findings: list[dict[str, Any]],
    *,
    category: str,
    severity: str,
    title: str,
    file_path: str,
    line: int,
    description: str,
    evidence: str,
    recommendation: str,
) -> None:
    findings.append(
        {
            "category": category,
            "severity": severity,
            "title": title,
            "file_path": file_path,
            "line": line,
            "description": description,
            "evidence": evidence,
            "recommendation": recommendation,
        }
    )


# ------------------------------------------------------------------
# SECURITY
# ------------------------------------------------------------------


def scan_security(
    source: str,
    path: str,
    findings: list[dict[str, Any]],
) -> None:
    lines = source.splitlines()

    patterns = [
        (
            r"\beval\s*\(",
            "Use of eval()",
            "critical",
            "eval() executes dynamically supplied Python expressions and can become a code-execution vulnerability.",
            "Replace dynamic evaluation with explicit parsing or dispatch logic.",
        ),
        (
            r"\bexec\s*\(",
            "Use of exec()",
            "critical",
            "exec() executes dynamically constructed Python code.",
            "Remove exec() and use explicit functions or safe alternatives.",
        ),
        (
            r"\bsubprocess\.(run|Popen|call|check_output)\s*\(",
            "Subprocess execution",
            "medium",
            "The code invokes an operating-system subprocess. This requires careful input validation.",
            "Ensure command arguments are passed safely and avoid shell interpretation of untrusted input.",
        ),
        (
            r"shell\s*=\s*True",
            "Shell execution enabled",
            "high",
            "shell=True allows command strings to be interpreted by a shell and increases command-injection risk.",
            "Prefer shell=False and pass command arguments as a list.",
        ),
        (
            r"verify\s*=\s*False",
            "TLS verification disabled",
            "high",
            "TLS certificate verification is disabled.",
            "Keep certificate verification enabled unless there is a documented controlled exception.",
        ),
        (
            r"(password|passwd|pwd)\s*=\s*[\"'][^\"']+[\"']",
            "Hard-coded password",
            "high",
            "A password-like value appears to be embedded directly in source code.",
            "Move credentials to environment variables or a secret manager.",
        ),
        (
            r"(api[_-]?key|secret[_-]?key|access[_-]?token)\s*=\s*[\"'][^\"']+[\"']",
            "Hard-coded credential",
            "high",
            "A credential-like value appears to be embedded directly in source code.",
            "Move credentials to environment variables or a secret manager.",
        ),
    ]

    for number, line in enumerate(lines, start=1):
        stripped = line.strip()

        if not stripped:
            continue

        for (
            pattern,
            title,
            severity,
            description,
            recommendation,
        ) in patterns:
            if re.search(
                pattern,
                stripped,
                re.IGNORECASE,
            ):
                add_finding(
                    findings,
                    category="security",
                    severity=severity,
                    title=title,
                    file_path=path,
                    line=number,
                    description=description,
                    evidence=stripped,
                    recommendation=recommendation,
                )


# ------------------------------------------------------------------
# PYTHON AST ANALYSIS
# ------------------------------------------------------------------


def scan_python_ast(
    source: str,
    path: str,
    findings: list[dict[str, Any]],
    functions: list[dict[str, Any]],
) -> None:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return

    class Visitor(ast.NodeVisitor):
        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            end_line = int(
                getattr(
                    node,
                    "end_lineno",
                    node.lineno,
                )
            )

            functions.append(
                {
                    "path": path,
                    "name": node.name,
                    "line": node.lineno,
                    "end_line": end_line,
                    "node": node,
                }
            )

            complexity = 1

            for child in ast.walk(node):
                if isinstance(
                    child,
                    (
                        ast.If,
                        ast.For,
                        ast.While,
                        ast.Try,
                        ast.With,
                        ast.ExceptHandler,
                        ast.IfExp,
                        ast.BoolOp,
                        ast.comprehension,
                    ),
                ):
                    complexity += 1

            if complexity >= 15:
                add_finding(
                    findings,
                    category="complexity",
                    severity="high",
                    title="High function complexity",
                    file_path=path,
                    line=node_line(node),
                    description=(
                        f"Function '{node.name}' has an estimated "
                        f"control-flow complexity of {complexity}."
                    ),
                    evidence=f"Function: {node.name}",
                    recommendation=(
                        "Split the function into smaller units and "
                        "simplify branching and nested control flow."
                    ),
                )
            elif complexity >= 9:
                add_finding(
                    findings,
                    category="complexity",
                    severity="medium",
                    title="Elevated function complexity",
                    file_path=path,
                    line=node_line(node),
                    description=(
                        f"Function '{node.name}' has an estimated "
                        f"control-flow complexity of {complexity}."
                    ),
                    evidence=f"Function: {node.name}",
                    recommendation=(
                        "Consider extracting conditional or looping "
                        "logic into focused helper functions."
                    ),
                )

            statement_count = len(node.body)

            if statement_count >= 80:
                add_finding(
                    findings,
                    category="code_smell",
                    severity="medium",
                    title="Very large function",
                    file_path=path,
                    line=node_line(node),
                    description=(
                        f"Function '{node.name}' contains "
                        f"{statement_count} top-level statements."
                    ),
                    evidence=f"Function: {node.name}",
                    recommendation=(
                        "Split the function into smaller functions "
                        "with single responsibilities."
                    ),
                )

            self.generic_visit(node)

        def visit_AsyncFunctionDef(
            self,
            node: ast.AsyncFunctionDef,
        ) -> None:
            self.visit_FunctionDef(
                node  # type: ignore[arg-type]
            )

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            member_count = len(node.body)

            if member_count >= 30:
                add_finding(
                    findings,
                    category="code_smell",
                    severity="medium",
                    title="Large class",
                    file_path=path,
                    line=node_line(node),
                    description=(
                        f"Class '{node.name}' contains "
                        f"{member_count} top-level members."
                    ),
                    evidence=f"Class: {node.name}",
                    recommendation=(
                        "Split responsibilities into smaller classes "
                        "or focused services."
                    ),
                )

            self.generic_visit(node)

        def visit_ExceptHandler(
            self,
            node: ast.ExceptHandler,
        ) -> None:
            if node.type is None:
                add_finding(
                    findings,
                    category="code_smell",
                    severity="medium",
                    title="Bare exception handler",
                    file_path=path,
                    line=node_line(node),
                    description=(
                        "A bare except catches every exception and can "
                        "hide unexpected application failures."
                    ),
                    evidence="except:",
                    recommendation=(
                        "Catch the specific exceptions you expect."
                    ),
                )

            self.generic_visit(node)

        def visit_ImportFrom(
            self,
            node: ast.ImportFrom,
        ) -> None:
            for alias in node.names:
                if alias.name == "*":
                    add_finding(
                        findings,
                        category="code_smell",
                        severity="low",
                        title="Wildcard import",
                        file_path=path,
                        line=node_line(node),
                        description=(
                            "Wildcard imports make dependencies implicit "
                            "and can create name collisions."
                        ),
                        evidence=(
                            f"from {node.module or 'module'} import *"
                        ),
                        recommendation=(
                            "Import only the names that are actually used."
                        ),
                    )

            self.generic_visit(node)

    Visitor().visit(tree)


# ------------------------------------------------------------------
# DUPLICATE LOGIC
# ------------------------------------------------------------------


def normalized_ast_hash(node: ast.AST) -> str:
    """
    Generate a stable hash from a function's AST.

    Source locations are ignored so identical implementations can
    be compared independent of line number.
    """

    payload = ast.dump(
        node,
        annotate_fields=True,
        include_attributes=False,
    )

    payload = re.sub(
        r"FunctionDef\([^)]*name='[^']+'",
        "FunctionDef(name='__FUNCTION__'",
        payload,
    )

    payload = re.sub(
        r"AsyncFunctionDef\([^)]*name='[^']+'",
        "AsyncFunctionDef(name='__FUNCTION__'",
        payload,
    )

    return hashlib.sha256(
        payload.encode("utf-8")
    ).hexdigest()


def scan_duplicate_functions(
    functions: list[dict[str, Any]],
    findings: list[dict[str, Any]],
) -> None:
    buckets: dict[
        str,
        list[dict[str, Any]],
    ] = defaultdict(list)

    for function in functions:
        node = function.get("node")

        if node is None:
            continue

        # Ignore tiny functions because matching very small helpers
        # produces low-value duplicate warnings.
        if len(getattr(node, "body", [])) < 5:
            continue

        try:
            digest = normalized_ast_hash(node)
        except Exception:
            continue

        buckets[digest].append(function)

    emitted: set[
        tuple[tuple[str, int], ...]
    ] = set()

    for locations in buckets.values():
        if len(locations) < 2:
            continue

        identity = tuple(
            sorted(
                (
                    item["path"],
                    item["line"],
                )
                for item in locations
            )
        )

        if identity in emitted:
            continue

        emitted.add(identity)

        first = locations[0]

        evidence = "; ".join(
            f"{item['path']}:{item['line']}"
            for item in locations[:6]
        )

        add_finding(
            findings,
            category="duplicate_logic",
            severity="medium",
            title="Duplicate function implementation",
            file_path=first["path"],
            line=first["line"],
            description=(
                f"Function '{first['name']}' has the same normalized "
                "AST structure as another function."
            ),
            evidence=evidence,
            recommendation=(
                "Consider extracting the shared behavior into a "
                "reusable function or service."
            ),
        )


# ------------------------------------------------------------------
# TEST ANALYSIS
# ------------------------------------------------------------------


def is_test_file(path: str) -> bool:
    name = Path(path).name.lower()

    return (
        name.startswith("test_")
        or name.endswith("_test.py")
        or ".test." in name
        or ".spec." in name
    )


def collect_test_text(root: str) -> str:
    parts: list[str] = []

    for path in iter_source_files(root):
        relative = relative_path(root, path)

        if is_test_file(relative):
            parts.append(
                read_text(path)
            )

    return "\n".join(parts)


def scan_missing_tests(
    root: str,
    functions: list[dict[str, Any]],
    findings: list[dict[str, Any]],
) -> None:
    test_text = collect_test_text(root)

    if not test_text.strip():
        add_finding(
            findings,
            category="missing_tests",
            severity="medium",
            title="No test files detected",
            file_path=".",
            line=1,
            description=(
                "No files matching common test naming conventions "
                "were detected."
            ),
            evidence="No test files found.",
            recommendation=(
                "Add automated tests for core application behavior."
            ),
        )
        return

    framework_functions = {
        "startup",
        "shutdown",
        "lifespan",
        "create_tables",
        "health_check",
        "database_health_check",
    }

    for function in functions:
        name = function["name"]

        if name.startswith("_"):
            continue

        if name in framework_functions:
            continue

        node = function.get("node")

        if node is not None and len(
            getattr(node, "body", [])
        ) < 4:
            continue

        if re.search(
            rf"\b{re.escape(name)}\b",
            test_text,
        ):
            continue

        add_finding(
            findings,
            category="missing_tests",
            severity="low",
            title="No obvious test coverage",
            file_path=function["path"],
            line=function["line"],
            description=(
                f"No reference to function '{name}' was found "
                "inside detected test files."
            ),
            evidence=f"Function: {name}",
            recommendation=(
                f"Add a focused test covering '{name}' and "
                "important edge cases."
            ),
        )


# ------------------------------------------------------------------
# DEAD CODE
# ------------------------------------------------------------------


def scan_dead_code(
    root: str,
    functions: list[dict[str, Any]],
    findings: list[dict[str, Any]],
) -> None:
    all_source_parts: list[str] = []

    for path in iter_source_files(root):
        all_source_parts.append(
            read_text(path)
        )

    all_source = "\n".join(
        all_source_parts
    )

    framework_entry_points = {
        "chat",
        "chat_stream",
        "create_repository",
        "list_repositories",
        "get_repository",
        "repository_status",
        "index",
        "health_check",
        "database_health_check",
        "create_tables",
    }

    for function in functions:
        name = function["name"]

        if name.startswith("_"):
            continue

        if name in framework_entry_points:
            continue

        occurrences = len(
            re.findall(
                rf"\b{re.escape(name)}\b",
                all_source,
            )
        )

        if occurrences != 1:
            continue

        add_finding(
            findings,
            category="dead_code",
            severity="low",
            title="Possibly unused function",
            file_path=function["path"],
            line=function["line"],
            description=(
                f"Function '{name}' appears only at its definition "
                "across the scanned source."
            ),
            evidence=f"Function: {name}",
            recommendation=(
                "Confirm whether this function is still needed. "
                "Remove it if it is obsolete."
            ),
        )


# ------------------------------------------------------------------
# DEDUPLICATE FINDINGS
# ------------------------------------------------------------------


def deduplicate_findings(
    findings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    seen = set()
    result = []

    for finding in findings:
        key = (
            finding.get("category"),
            finding.get("severity"),
            finding.get("title"),
            finding.get("file_path"),
            finding.get("line"),
            finding.get("evidence"),
        )

        if key in seen:
            continue

        seen.add(key)
        result.append(finding)

    return result


# ------------------------------------------------------------------
# MAIN ANALYZER
# ------------------------------------------------------------------


def analyze_repository(
    local_path: str,
) -> dict[str, Any]:
    root = str(
        Path(local_path).resolve()
    )

    findings: list[dict[str, Any]] = []
    functions: list[dict[str, Any]] = []

    source_files = list(
        iter_source_files(root)
    )

    for path in source_files:
        source = read_text(path)

        relative = relative_path(
            root,
            path,
        )

        scan_security(
            source,
            relative,
            findings,
        )

        if path.suffix.lower() == ".py":
            scan_python_ast(
                source,
                relative,
                findings,
                functions,
            )

    scan_duplicate_functions(
        functions,
        findings,
    )

    scan_missing_tests(
        root,
        functions,
        findings,
    )

    scan_dead_code(
        root,
        functions,
        findings,
    )

    findings = deduplicate_findings(
        findings
    )

    severity_order = {
        "critical": 0,
        "high": 1,
        "medium": 2,
        "low": 3,
    }

    findings.sort(
        key=lambda item: (
            severity_order.get(
                item["severity"],
                9,
            ),
            item["category"],
            item["file_path"],
            item["line"],
        )
    )

    category_counts: dict[str, int] = defaultdict(int)
    severity_counts: dict[str, int] = defaultdict(int)

    for finding in findings:
        category_counts[
            finding["category"]
        ] += 1

        severity_counts[
            finding["severity"]
        ] += 1

    score = 100

    score -= (
        severity_counts["critical"] * 20
    )

    score -= (
        severity_counts["high"] * 10
    )

    score -= (
        severity_counts["medium"] * 4
    )

    score -= (
        severity_counts["low"] * 1
    )

    score = max(
        0,
        min(100, score),
    )

    if score >= 90:
        health = "excellent"
    elif score >= 75:
        health = "good"
    elif score >= 55:
        health = "needs_attention"
    else:
        health = "poor"

    return {
        "score": score,
        "health": health,
        "files_scanned": len(source_files),
        "functions_scanned": len(functions),
        "categories": dict(category_counts),
        "severity": dict(severity_counts),
        "findings": findings[:200],
    }