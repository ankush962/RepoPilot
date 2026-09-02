import json
import re
from pathlib import Path

from git import Repo, GitCommandError
import ollama

from app.config import settings


PR_REF_PATTERN = re.compile(r"^[1-9][0-9]{0,6}$")

OLLAMA = ollama.Client(
    host=settings.ollama_url,
    timeout=settings.ollama_timeout_seconds,
)


def validate_pr_number(pr_number: int) -> int:
    value = int(pr_number)

    if value < 1 or value > 9_999_999:
        raise ValueError("Invalid pull request number.")

    if not PR_REF_PATTERN.fullmatch(str(value)):
        raise ValueError("Invalid pull request number.")

    return value


def _is_test_file(path: str) -> bool:
    normalized = path.lower().replace("\\", "/")

    filename = Path(normalized).name

    return any(
        marker in normalized
        for marker in (
            "/tests/",
            "/test/",
            "/__tests__/",
            "/spec/",
        )
    ) or (
        filename.startswith("test_")
        or filename.endswith("_test.py")
        or ".test." in filename
        or ".spec." in filename
    )


def _fetch_pr(
    repo: Repo,
    pr_number: int,
) -> str:
    remote_ref = (
        f"refs/remotes/origin/"
        f"repopilot-pr-{pr_number}"
    )

    try:
        repo.git.fetch(
            "origin",
            f"pull/{pr_number}/head:{remote_ref}",
            "--force",
        )
    except GitCommandError as exc:
        raise RuntimeError(
            f"Unable to fetch pull request #{pr_number}: "
            f"{exc.stderr or exc}"
        ) from exc

    try:
        return repo.commit(remote_ref).hexsha
    except Exception as exc:
        raise RuntimeError(
            f"Pull request #{pr_number} could not be resolved."
        ) from exc


def _fetch_base(
    repo: Repo,
    base_branch: str,
) -> str:
    base_branch = base_branch.strip()

    if not base_branch:
        raise ValueError("Base branch is required.")

    try:
        repo.git.fetch(
            "origin",
            base_branch,
        )
    except GitCommandError as exc:
        raise RuntimeError(
            f"Unable to fetch base branch '{base_branch}': "
            f"{exc.stderr or exc}"
        ) from exc

    candidates = [
        f"origin/{base_branch}",
        base_branch,
    ]

    for candidate in candidates:
        try:
            return repo.commit(candidate).hexsha
        except Exception:
            continue

    raise RuntimeError(
        f"Base branch '{base_branch}' could not be resolved."
    )


def _changed_files(
    repo: Repo,
    base_sha: str,
    head_sha: str,
):
    raw = repo.git.diff(
        "--name-status",
        base_sha,
        head_sha,
    )

    files = []

    for line in raw.splitlines():
        if not line.strip():
            continue

        parts = line.split("\t")

        if len(parts) >= 3 and parts[0].startswith("R"):
            change_type = parts[0]
            old_path = parts[1]
            new_path = parts[2]
        elif len(parts) >= 2:
            change_type = parts[0]
            old_path = parts[1]
            new_path = parts[1]
        else:
            continue

        files.append(
            {
                "change_type": change_type,
                "old_path": old_path,
                "new_path": new_path,
                "is_test": _is_test_file(new_path),
            }
        )

    return files


def _commit_list(
    repo: Repo,
    base_sha: str,
    head_sha: str,
):
    commits = []

    for commit in repo.iter_commits(
        f"{base_sha}..{head_sha}"
    ):
        commits.append(
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
        )

    return commits


def _diff_stats(
    repo: Repo,
    base_sha: str,
    head_sha: str,
):
    raw = repo.git.diff(
        "--numstat",
        base_sha,
        head_sha,
    )

    additions = 0
    deletions = 0
    files = 0

    for line in raw.splitlines():
        parts = line.split("\t")

        if len(parts) < 3:
            continue

        files += 1

        try:
            additions += int(parts[0])
        except ValueError:
            pass

        try:
            deletions += int(parts[1])
        except ValueError:
            pass

    return {
        "files": files,
        "additions": additions,
        "deletions": deletions,
    }


def _build_review_prompt(
    pr_number: int,
    base_branch: str,
    base_sha: str,
    head_sha: str,
    changed_files,
    commits,
    diff_text: str,
    tests_changed: bool,
) -> str:
    changed_file_lines = "\n".join(
        (
            f"- {item['change_type']} "
            f"{item['new_path']}"
        )
        for item in changed_files
    )

    commit_lines = "\n".join(
        (
            f"- {commit['short_sha']}: "
            f"{commit['message']}"
        )
        for commit in commits
    )

    return f"""
You are reviewing GitHub pull request #{pr_number}.

Base branch:
{base_branch}

Base commit:
{base_sha}

PR head commit:
{head_sha}

CHANGED FILES:
{changed_file_lines or "- none"}

COMMITS:
{commit_lines or "- none"}

TEST FILE CHANGED:
{"yes" if tests_changed else "no"}

DIFF:
{diff_text}

Perform a focused code review.

Return ONLY valid JSON with this exact structure:

{{
  "summary": "brief summary",
  "risk_level": "low|medium|high|critical",
  "findings": [
    {{
      "severity": "low|medium|high|critical",
      "file_path": "path/to/file",
      "line": 1,
      "title": "short title",
      "problem": "what is wrong",
      "evidence": "specific evidence from the diff",
      "recommendation": "specific fix"
    }}
  ],
  "changed_code_explanation": [
    {{
      "file_path": "path/to/file",
      "explanation": "what changed and why it matters"
    }}
  ],
  "test_assessment": {{
    "tests_changed": true,
    "status": "adequate|partial|missing",
    "reason": "why"
  }},
  "review_comments": [
    {{
      "file_path": "path/to/file",
      "line": 1,
      "comment": "review comment suitable for a PR"
    }}
  ]
}}

Rules:

- Only report problems supported by the supplied diff.
- Do not invent files or code.
- Do not praise code without explaining something useful.
- Prefer actionable review comments.
- If there are no real bugs, findings should be an empty array.
- If no tests are changed, explicitly assess whether the changed behavior appears to require tests.
- Line numbers should refer to the changed file where reasonably determinable.
"""


def _parse_review_response(raw: str):
    text = raw.strip()

    if text.startswith("```"):
        text = re.sub(
            r"^```(?:json)?\s*",
            "",
            text,
            flags=re.IGNORECASE,
        )

        text = re.sub(
            r"\s*```$",
            "",
            text,
        )

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {
            "summary": text,
            "risk_level": "unknown",
            "findings": [],
            "changed_code_explanation": [],
            "test_assessment": {},
            "review_comments": [],
        }


def analyze_pull_request(
    repository_path: str,
    pr_number: int,
    base_branch: str = "main",
):
    pr_number = validate_pr_number(
        pr_number
    )

    repo = Repo(repository_path)

    if repo.bare:
        raise RuntimeError(
            "Repository checkout is invalid."
        )

    head_sha = _fetch_pr(
        repo,
        pr_number,
    )

    base_sha = _fetch_base(
        repo,
        base_branch,
    )

    changed_files = _changed_files(
        repo,
        base_sha,
        head_sha,
    )

    commits = _commit_list(
        repo,
        base_sha,
        head_sha,
    )

    stats = _diff_stats(
        repo,
        base_sha,
        head_sha,
    )

    diff_text = repo.git.diff(
        "--no-ext-diff",
        "--unified=60",
        base_sha,
        head_sha,
    )

    max_diff_chars = 40_000

    if len(diff_text) > max_diff_chars:
        diff_text = (
            diff_text[:max_diff_chars]
            + "\n\n...[diff truncated]"
        )

    tests_changed = any(
        item["is_test"]
        for item in changed_files
    )

    prompt = _build_review_prompt(
        pr_number=pr_number,
        base_branch=base_branch,
        base_sha=base_sha,
        head_sha=head_sha,
        changed_files=changed_files,
        commits=commits,
        diff_text=diff_text,
        tests_changed=tests_changed,
    )

    try:
        response = OLLAMA.chat(
            model=settings.ollama_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are RepoPilot PR Assistant. "
                        "Review only the supplied pull request diff."
                    ),
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

        raw_answer = (
            response
            .get("message", {})
            .get("content", "")
            .strip()
        )

    except Exception as exc:
        raise RuntimeError(
            f"Unable to analyze pull request with Ollama: {exc}"
        ) from exc

    review = _parse_review_response(
        raw_answer
    )

    return {
        "pull_request": pr_number,
        "base": {
            "branch": base_branch,
            "commit": base_sha,
        },
        "head": {
            "commit": head_sha,
        },
        "statistics": stats,
        "files": changed_files,
        "commits": commits,
        "tests": {
            "changed": tests_changed,
            "status": (
                "tests_changed"
                if tests_changed
                else "no_test_files_changed"
            ),
        },
        "review": review,
    }