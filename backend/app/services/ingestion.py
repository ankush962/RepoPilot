from __future__ import annotations

import ipaddress
import os
import socket
import tempfile
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlparse

from git import Repo
from sqlalchemy.orm import Session

from app.config import settings
from app.models import CodeChunk, Repository
from app.services.chunker import iter_code_files, chunk_file


# ------------------------------------------------------------------
# REPOSITORY URL SECURITY
# ------------------------------------------------------------------

ALLOWED_GIT_SCHEMES = {
    "https",
    "http",
}

BLOCKED_HOSTNAMES = {
    "localhost",
    "localhost.localdomain",
    "ip6-localhost",
    "ip6-loopback",
    "ip6-localnet",
    "0.0.0.0",
    "::1",
    "169.254.169.254",
    "metadata.google.internal",
    "metadata.google",
}


def _is_private_or_reserved_ip(address: str) -> bool:
    """
    Return True for loopback, private, link-local, multicast,
    reserved, unspecified, or otherwise non-public addresses.
    """
    try:
        ip = ipaddress.ip_address(address)

        return (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        )
    except ValueError:
        return False


def _host_resolves_to_private_network(hostname: str) -> bool:
    """
    Resolve a hostname and reject it if any resolved IP points to
    a private/reserved network.

    This provides an additional SSRF defense beyond hostname
    blocklisting.
    """
    try:
        addresses = socket.getaddrinfo(
            hostname,
            None,
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror:
        # Let Git produce the normal connection error later.
        return False

    for result in addresses:
        sockaddr = result[4]

        if not sockaddr:
            continue

        address = sockaddr[0]

        if _is_private_or_reserved_ip(address):
            return True

    return False


def validate_repository_url(url: str) -> str:
    """
    Validate an externally supplied Git repository URL.

    Only HTTP(S) URLs are accepted. Localhost, metadata endpoints,
    private IPs and reserved networks are rejected.
    """
    if not isinstance(url, str):
        raise ValueError("Repository URL must be a string.")

    url = url.strip()

    if not url:
        raise ValueError("Repository URL is required.")

    parsed = urlparse(url)

    # Only allow HTTP(S).
    if parsed.scheme.lower() not in ALLOWED_GIT_SCHEMES:
        raise ValueError(
            "Only HTTP(S) Git repository URLs are allowed."
        )

    # Userinfo can be abused in confusing URLs such as:
    # https://evil.com@localhost/repo.git
    if parsed.username or parsed.password:
        raise ValueError(
            "Repository URLs containing credentials are not allowed."
        )

    hostname = parsed.hostname

    if not hostname:
        raise ValueError(
            "Repository URL must contain a valid hostname."
        )

    hostname = hostname.lower().rstrip(".")

    if hostname in BLOCKED_HOSTNAMES:
        raise ValueError(
            "Repository host is not allowed."
        )

    # Direct IP address check.
    if _is_private_or_reserved_ip(hostname):
        raise ValueError(
            "Repository host is not allowed."
        )

    # DNS-based private-network protection.
    if _host_resolves_to_private_network(hostname):
        raise ValueError(
            "Repository host resolves to a private or reserved network."
        )

    # Avoid malformed URLs with no meaningful path.
    if not parsed.path or parsed.path == "/":
        raise ValueError(
            "Repository URL must point to a Git repository."
        )

    return url


# ------------------------------------------------------------------
# HELPERS
# ------------------------------------------------------------------


def repository_name(url: str) -> str:
    """
    Extract a repository name from a Git URL.
    """
    value = url.rstrip("/").split("/")[-1]

    return (
        value[:-4]
        if value.endswith(".git")
        else value
    )


@contextmanager
def github_git_environment():
    """
    Provide GitHub credentials through GIT_ASKPASS instead of
    embedding credentials in repository URLs or Git command
    arguments.

    When GITHUB_TOKEN is not configured, Git runs normally and
    public repositories continue to work.
    """
    token = (settings.github_token or "").strip()

    if not token:
        yield None
        return

    fd, askpass_path = tempfile.mkstemp(
        prefix="repopilot-git-askpass-",
        text=True,
    )

    try:
        with os.fdopen(
            fd,
            "w",
            encoding="utf-8",
        ) as file:
            file.write(
                "#!/bin/sh\n"
                'case "$1" in\n'
                '  *Username*) printf "%s\\n" "x-access-token" ;;\n'
                '  *Password*) printf "%s\\n" "$REPOPILOT_GITHUB_TOKEN" ;;\n'
                '  *) printf "%s\\n" "$REPOPILOT_GITHUB_TOKEN" ;;\n'
                "esac\n"
            )

        os.chmod(
            askpass_path,
            0o700,
        )

        env = os.environ.copy()
        env["GIT_ASKPASS"] = askpass_path
        env["GIT_TERMINAL_PROMPT"] = "0"
        env["REPOPILOT_GITHUB_TOKEN"] = token

        yield env

    finally:
        try:
            os.unlink(askpass_path)
        except FileNotFoundError:
            pass


def get_remote_commit(
    repo: Repo,
    branch: str,
) -> str:
    """
    Fetch the remote branch and return its latest commit SHA.

    GitHub credentials are supplied through GIT_ASKPASS when
    configured.
    """
    with github_git_environment() as git_env:
        if git_env:
            with repo.git.custom_environment(
                GIT_ASKPASS=git_env["GIT_ASKPASS"],
                GIT_TERMINAL_PROMPT=git_env["GIT_TERMINAL_PROMPT"],
                REPOPILOT_GITHUB_TOKEN=git_env[
                    "REPOPILOT_GITHUB_TOKEN"
                ],
            ):
                repo.git.fetch(
                    "origin",
                    branch,
                    "--prune",
                )
        else:
            repo.git.fetch(
                "origin",
                branch,
                "--prune",
            )

    return repo.commit(
        f"origin/{branch}"
    ).hexsha


# ------------------------------------------------------------------
# INDEX REPOSITORY
# ------------------------------------------------------------------


def index_repository(
    db: Session,
    repository: Repository,
    progress=None,
):
    """
    Clone/update a repository and incrementally index its source files.

    Existing chunks are reused by content hash. Removed chunks are
    deleted. New chunks are inserted without destroying unchanged
    data.

    Returns metadata describing the indexing operation.
    """
    workspace = Path(
        settings.workspace_dir
    ).resolve()

    workspace.mkdir(
        parents=True,
        exist_ok=True,
    )

    destination = (
        workspace / f"repo_{repository.id}"
    ).resolve()

    # Prevent path traversal through an unexpected workspace config.
    try:
        destination.relative_to(workspace)
    except ValueError as exc:
        raise ValueError(
            "Invalid repository workspace path."
        ) from exc

    def stage(
        percent: int,
        label: str,
    ):
        repository.status = "indexing"
        db.commit()

        if progress:
            progress(
                percent,
                label,
            )

    try:
        # ----------------------------------------------------------
        # Validate repository URL before any network operation.
        # ----------------------------------------------------------

        repository_url = validate_repository_url(
            repository.url
        )

        stage(
            5,
            "Fetching repository",
        )

        # ----------------------------------------------------------
        # EXISTING CLONE
        # ----------------------------------------------------------

        if destination.exists():
            # The directory must actually be a Git repository.
            if not (destination / ".git").exists():
                raise ValueError(
                    "Repository workspace exists but is not a Git repository."
                )

            repo = Repo(destination)

            # Verify the existing repository points at the expected
            # remote URL. This prevents accidentally indexing a
            # different repository from a reused workspace directory.
            try:
                configured_remote = repo.remote(
                    "origin"
                ).url
            except Exception as exc:
                raise ValueError(
                    "Existing repository has no valid origin remote."
                ) from exc

            if configured_remote != repository_url:
                raise ValueError(
                    "Existing repository remote does not match "
                    "the configured repository URL."
                )

            remote_commit = get_remote_commit(
                repo,
                repository.branch,
            )

            # No source changes since the previous successful index.
            if (
                repository.last_indexed_commit
                == remote_commit
            ):
                repository.local_path = str(
                    destination
                )

                repository.status = "indexed"

                db.commit()

                if progress:
                    progress(
                        100,
                        "Already up to date",
                    )

                return {
                    "chunks": 0,
                    "new_chunks": 0,
                    "changed": False,
                    "commit": remote_commit,
                }

            # Ensure the requested branch is checked out.
            repo.git.checkout(
                repository.branch
            )

            # Reset to the exact remote branch state.
            repo.git.reset(
                "--hard",
                f"origin/{repository.branch}",
            )

        # ----------------------------------------------------------
        # FIRST CLONE
        # ----------------------------------------------------------

        else:
            with github_git_environment() as git_env:
                Repo.clone_from(
                    repository_url,
                    str(destination),
                    branch=repository.branch,
                    env=git_env,
                )

            repo = Repo(destination)

            remote_commit = repo.commit(
                repository.branch
            ).hexsha

        repository.local_path = str(
            destination
        )

        db.commit()

        # ----------------------------------------------------------
        # ANALYZE SOURCE FILES
        # ----------------------------------------------------------

        stage(
            15,
            "Analyzing source files",
        )

        desired: list[dict] = []

        files = list(
            iter_code_files(destination)
        )

        total_files = max(
            1,
            len(files),
        )

        for index, file_path in enumerate(
            files,
            1,
        ):
            relative = str(
                file_path.relative_to(
                    destination
                )
            )

            for chunk in chunk_file(
                file_path
            ):
                content = (
                    chunk.get(
                        "content",
                        "",
                    ).strip()
                )

                if not content:
                    continue

                desired.append(
                    {
                        "file_path": relative,
                        **chunk,
                    }
                )

            if (
                progress
                and index
                % max(
                    1,
                    total_files // 10,
                )
                == 0
            ):
                progress(
                    min(
                        55,
                        15
                        + int(
                            index
                            / total_files
                            * 40
                        ),
                    ),
                    (
                        f"Chunking files "
                        f"({index}/{total_files})"
                    ),
                )

        # ----------------------------------------------------------
        # BUILD DESIRED CONTENT HASH SET
        # ----------------------------------------------------------

        desired_hashes = {
            item["content_hash"]
            for item in desired
            if item.get("content_hash")
        }

        existing = (
            db.query(CodeChunk)
            .filter(
                CodeChunk.repository_id
                == repository.id,
            )
            .all()
        )

        existing_by_hash = {
            chunk.content_hash: chunk
            for chunk in existing
            if chunk.content_hash
        }

        # ----------------------------------------------------------
        # REMOVE DELETED CHUNKS
        # ----------------------------------------------------------

        for old in existing:
            if (
                old.content_hash
                and old.content_hash
                not in desired_hashes
            ):
                db.delete(old)

        db.flush()

        # ----------------------------------------------------------
        # ADD NEW CHUNKS
        # ----------------------------------------------------------

        new_chunks: list[CodeChunk] = []

        for item in desired:
            content_hash = item.get(
                "content_hash"
            )

            if (
                content_hash
                and content_hash
                in existing_by_hash
            ):
                continue

            new_chunks.append(
                CodeChunk(
                    repository_id=repository.id,
                    file_path=item[
                        "file_path"
                    ],
                    start_line=item[
                        "start_line"
                    ],
                    end_line=item[
                        "end_line"
                    ],
                    content=item[
                        "content"
                    ],
                    content_hash=content_hash,
                    chunk_type=item.get(
                        "chunk_type",
                        "text",
                    ),
                )
            )

        if new_chunks:
            db.add_all(
                new_chunks
            )

        db.commit()

        # ----------------------------------------------------------
        # UPDATE REPOSITORY INDEX STATE
        # ----------------------------------------------------------

        repository.last_indexed_commit = (
            remote_commit
        )

        repository.status = "indexed"

        db.commit()

        if progress:
            progress(
                65,
                (
                    f"Prepared "
                    f"{len(new_chunks)} "
                    f"new chunks"
                ),
            )

        return {
            "chunks": len(desired),
            "new_chunks": len(new_chunks),
            "changed": True,
            "commit": remote_commit,
            "new_chunk_objects": new_chunks,
        }

    except Exception:
        db.rollback()

        # Best effort: mark repository as errored.
        try:
            repository.status = "error"
            db.commit()
        except Exception:
            db.rollback()

        raise


# ------------------------------------------------------------------
# UPDATE DETECTION
# ------------------------------------------------------------------


def repository_needs_update(
    repository: Repository,
) -> bool:
    """
    Determine whether the configured remote branch has changed
    since the last successful indexing operation.
    """
    if not repository.local_path:
        return True

    try:
        repository_url = validate_repository_url(
            repository.url
        )

        repo = Repo(
            repository.local_path
        )

        # Verify the local clone still belongs to the configured
        # repository.
        configured_remote = repo.remote(
            "origin"
        ).url

        if configured_remote != repository_url:
            return True

        return (
            repository.last_indexed_commit
            != get_remote_commit(
                repo,
                repository.branch,
            )
        )

    except Exception:
        return True