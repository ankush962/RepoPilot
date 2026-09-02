
from __future__ import annotations

from pathlib import Path
from typing import Any

from git import Repo


def open_repo(local_path: str) -> Repo:
    path = Path(local_path)

    if not path.exists():
        raise FileNotFoundError(
            f"Repository workspace does not exist: {local_path}"
        )

    return Repo(path)


def fetch_branch(repo: Repo, branch: str) -> str:
    repo.git.fetch(
        "origin",
        branch,
        "--prune",
    )

    return repo.commit(
        f"origin/{branch}"
    ).hexsha


def current_remote_commit(
    local_path: str,
    branch: str,
) -> str:
    repo = open_repo(local_path)
    return fetch_branch(repo, branch)


def resolve_ref(repo: Repo, ref: str):
    """
    Resolve a Git ref robustly.

    Tries:
    - exact ref
    - origin/<ref>
    - refs/heads/<ref>
    - refs/remotes/origin/<ref>
    """
    candidates = [
        ref,
        f"origin/{ref}",
        f"refs/heads/{ref}",
        f"refs/remotes/origin/{ref}",
    ]

    for candidate in candidates:
        try:
            return repo.commit(candidate)
        except Exception:
            continue

    raise ValueError(
        f"Ref '{ref}' did not resolve to an object"
    )


def changed_files(
    local_path: str,
    base_commit: str,
    target_commit: str,
) -> list[dict[str, Any]]:
    repo = open_repo(local_path)

    base = resolve_ref(
        repo,
        base_commit,
    )

    target = resolve_ref(
        repo,
        target_commit,
    )

    diff = base.diff(
        target,
        create_patch=False,
    )

    results = []

    for item in diff:
        results.append(
            {
                "change_type": item.change_type,
                "old_path": item.a_path,
                "new_path": item.b_path,
            }
        )

    return results


def compare_refs(
    local_path: str,
    base: str,
    target: str,
) -> dict[str, Any]:
    repo = open_repo(local_path)

    # Refresh remote refs.
    repo.git.fetch(
        "origin",
        "--prune",
    )

    base_commit = resolve_ref(
        repo,
        base,
    )

    target_commit = resolve_ref(
        repo,
        target,
    )

    diff = base_commit.diff(
        target_commit,
        create_patch=False,
    )

    files = []

    for item in diff:
        files.append(
            {
                "change_type": item.change_type,
                "old_path": item.a_path,
                "new_path": item.b_path,
            }
        )

    commits = list(
        repo.iter_commits(
            f"{base_commit.hexsha}..{target_commit.hexsha}"
        )
    )

    commit_list = [
        {
            "sha": commit.hexsha,
            "short_sha": commit.hexsha[:12],
            "message": commit.message.strip(),
            "author": (
                commit.author.name
                if commit.author
                else None
            ),
            "committed_at": (
                commit.committed_datetime.isoformat()
                if commit.committed_datetime
                else None
            ),
        }
        for commit in commits
    ]

    return {
        "base": base,
        "target": target,
        "base_commit": base_commit.hexsha,
        "target_commit": target_commit.hexsha,
        "files": files,
        "commits": commit_list,
        "files_changed": len(files),
        "commits_count": len(commit_list),
    }


def commit_info(
    local_path: str,
    commit_sha: str,
) -> dict[str, Any]:
    repo = open_repo(local_path)

    commit = resolve_ref(
        repo,
        commit_sha,
    )

    parents = commit.parents

    if parents:
        diff = parents[0].diff(
            commit,
            create_patch=False,
        )
    else:
        diff = commit.diff(
            None,
            create_patch=False,
        )

    files = []

    for item in diff:
        files.append(
            {
                "change_type": item.change_type,
                "old_path": item.a_path,
                "new_path": item.b_path,
            }
        )

    return {
        "sha": commit.hexsha,
        "short_sha": commit.hexsha[:12],
        "message": commit.message.strip(),
        "author": (
            commit.author.name
            if commit.author
            else None
        ),
        "email": (
            commit.author.email
            if commit.author
            else None
        ),
        "committed_at": (
            commit.committed_datetime.isoformat()
            if commit.committed_datetime
            else None
        ),
        "files": files,
    }


def commit_context(
    local_path: str,
    commit_sha: str,
    max_files: int = 12,
    max_lines_per_file: int = 240,
) -> str:
    repo = open_repo(local_path)

    commit = resolve_ref(
        repo,
        commit_sha,
    )

    parts = [
        f"COMMIT: {commit.hexsha}",
        f"MESSAGE: {commit.message.strip()}",
    ]

    files = []

    if commit.parents:
        files = list(
            commit.parents[0].diff(
                commit,
                create_patch=False,
            )
        )

    for item in files[:max_files]:
        path = item.b_path or item.a_path

        if not path:
            continue

        try:
            blob = commit.tree / path

            content = (
                blob.data_stream
                .read()
                .decode(
                    "utf-8",
                    errors="replace",
                )
            )
        except Exception:
            continue

        lines = content.splitlines()

        if len(lines) > max_lines_per_file:
            lines = lines[:max_lines_per_file]
            lines.append(
                "...[truncated]"
            )

        parts.append(
            f"\nFILE: {path}\n"
            f"COMMIT: {commit.hexsha[:12]}\n\n"
            + "\n".join(lines)
        )

    return "\n".join(parts)
