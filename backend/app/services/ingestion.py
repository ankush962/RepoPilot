from pathlib import Path

from git import Repo
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Repository, CodeChunk
from app.services.chunker import iter_code_files, chunk_file


def repository_name(url: str) -> str:
    value = url.rstrip("/").split("/")[-1]

    if value.endswith(".git"):
        value = value[:-4]

    return value


def get_remote_commit(repo: Repo, branch: str) -> str:
    """
    Return the latest commit for the selected branch.
    """

    repo.git.fetch("origin", branch)

    return repo.commit(f"origin/{branch}").hexsha


def index_repository(
    db: Session,
    repository: Repository,
):
    """
    Clone/update repository and index its code.

    Returns number of chunks processed.

    If the remote commit hasn't changed since the previous
    indexing operation, no work is performed.
    """

    workspace = Path(settings.workspace_dir).resolve()
    workspace.mkdir(
        parents=True,
        exist_ok=True,
    )

    destination = workspace / f"repo_{repository.id}"

    try:
        # ---------------------------------------------------------
        # CLONE OR UPDATE
        # ---------------------------------------------------------

        if destination.exists():
            repo = Repo(destination)

            repo.git.fetch(
                "origin",
                repository.branch,
            )

            remote_commit = get_remote_commit(
                repo,
                repository.branch,
            )

            # Nothing changed.
            if (
                repository.last_indexed_commit
                and repository.last_indexed_commit == remote_commit
            ):
                repository.status = "indexed"
                db.commit()

                return 0

            repo.git.checkout(repository.branch)

            repo.git.reset(
                "--hard",
                f"origin/{repository.branch}",
            )

        else:
            Repo.clone_from(
                repository.url,
                destination,
                branch=repository.branch,
            )

            repo = Repo(destination)

            remote_commit = repo.commit(
                repository.branch
            ).hexsha

        repository.local_path = str(destination)
        repository.status = "indexing"

        db.commit()

        # ---------------------------------------------------------
        # REMOVE OLD CHUNKS
        # ---------------------------------------------------------

        db.query(CodeChunk).filter(
            CodeChunk.repository_id == repository.id
        ).delete()

        db.commit()

        # ---------------------------------------------------------
        # CHUNK SOURCE CODE
        # ---------------------------------------------------------

        count = 0

        for file_path in iter_code_files(destination):

            for chunk in chunk_file(file_path):

                relative_path = str(
                    file_path.relative_to(destination)
                )

                db.add(
                    CodeChunk(
                        repository_id=repository.id,
                        file_path=relative_path,
                        start_line=chunk["start_line"],
                        end_line=chunk["end_line"],
                        content=chunk["content"],
                    )
                )

                count += 1

        # ---------------------------------------------------------
        # SAVE INDEX STATE
        # ---------------------------------------------------------

        repository.last_indexed_commit = remote_commit
        repository.status = "indexed"

        db.commit()

        return count

    except Exception:
        repository.status = "error"
        db.commit()

        raise


def repository_needs_update(
    repository: Repository,
) -> bool:

    if not repository.local_path:
        return True

    try:
        repo = Repo(repository.local_path)

        remote_commit = get_remote_commit(
            repo,
            repository.branch,
        )

        return (
            repository.last_indexed_commit
            != remote_commit
        )

    except Exception:
        return True