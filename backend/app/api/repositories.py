from pathlib import Path
from urllib.parse import urlparse
import re
from sqlalchemy import text
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    CodeChunk,
    IndexJob,
    Repository,
    User,
    WorkspaceMembership,
)
from app.schemas import (
    GitCommitResponse,
    GitCompareResponse,
    IndexJobResponse,
    PullRequestAnalyzeRequest,
    RepositoryCreate,
    RepositoryResponse,
)
from app.services.architecture import architecture_report
from app.services.auth import require_user
from app.services.code_quality import analyze_repository
from app.services.git import (
    commit_info,
    compare_refs,
    current_remote_commit,
)
from app.services.ingestion import (
    repository_name,
    repository_needs_update,
)
from app.services.pr_assistant import analyze_pull_request
from app.services.workspaces import (
    get_repository_for_user,
    require_permission,
)


router = APIRouter(
    prefix="/repositories",
    tags=["repositories"],
)


# ------------------------------------------------------------------
# HELPERS
# ------------------------------------------------------------------

def get_owned_repository(
    repository_id: int,
    db: Session,
    user: User,
) -> Repository:
    """
    Resolve a repository through workspace membership.

    Legacy repositories without workspace_id remain accessible
    through the workspace-aware repository resolver.
    """
    return get_repository_for_user(
        db,
        repository_id,
        user,
    )


def repository_is_accessible(
    db: Session,
    repository_id: int,
    user: User,
) -> Repository:
    """
    Backwards-compatible alias used by route handlers.
    """
    return get_owned_repository(
        repository_id,
        db,
        user,
    )


def get_default_workspace(
    db: Session,
    user: User,
) -> WorkspaceMembership:
    """
    Return the first workspace in which the user can create
    repositories.

    Viewers cannot create repositories.
    """
    memberships = (
        db.query(WorkspaceMembership)
        .filter(
            WorkspaceMembership.user_id == user.id,
            WorkspaceMembership.role.in_(
                ["owner", "admin", "member"]
            ),
        )
        .order_by(
            WorkspaceMembership.id.asc()
        )
        .all()
    )

    if not memberships:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to add repositories.",
        )

    return memberships[0]


def resolve_workspace_for_create(
    db: Session,
    user: User,
    workspace_id: int | None,
) -> int:
    """
    Resolve and authorize the workspace used for a new repository.
    """
    if workspace_id is None:
        membership = get_default_workspace(
            db,
            user,
        )

        require_permission(
            db,
            membership.workspace_id,
            user,
            "add_repository",
        )

        return membership.workspace_id

    require_permission(
        db,
        workspace_id,
        user,
        "add_repository",
    )

    return workspace_id


# ------------------------------------------------------------------
# CREATE REPOSITORY
# ------------------------------------------------------------------

@router.post(
    "",
    response_model=RepositoryResponse,
    status_code=status.HTTP_200_OK,
)
def create_repository(
    payload: RepositoryCreate,
    workspace_id: int | None = Query(
        default=None,
    ),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    url = str(payload.url).strip()
    branch = payload.branch.strip() or "main"

    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()

    if host not in {
        "github.com",
        "www.github.com",
    }:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Only GitHub HTTPS repositories "
                "are supported."
            ),
        )

    if parsed.scheme != "https":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Repository URL must use HTTPS.",
        )

    if not re.fullmatch(
        r"[A-Za-z0-9._/-]+",
        branch,
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid branch name.",
        )

    target_workspace_id = resolve_workspace_for_create(
        db,
        user,
        workspace_id,
    )

    existing = (
        db.query(Repository)
        .filter(
            Repository.url == url,
            Repository.workspace_id == target_workspace_id,
        )
        .first()
    )

    if existing:
        return existing

    repo = Repository(
        name=repository_name(url),
        url=url,
        branch=branch,
        owner_username=user.username,
        workspace_id=target_workspace_id,
    )

    db.add(repo)
    db.commit()
    db.refresh(repo)

    return repo


# ------------------------------------------------------------------
# LIST REPOSITORIES
# ------------------------------------------------------------------

@router.get(
    "",
    response_model=list[RepositoryResponse],
)
def list_repositories(
    workspace_id: int | None = Query(
        default=None,
    ),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """
    Return repositories visible to the authenticated user.

    With workspace_id supplied, only repositories belonging to
    that workspace are returned.

    Legacy repositories with no workspace_id remain visible when
    owned by the authenticated user.
    """
    workspace_ids = (
        db.query(
            WorkspaceMembership.workspace_id
        )
        .filter(
            WorkspaceMembership.user_id == user.id,
        )
        .subquery()
    )

    query = db.query(Repository).filter(
        or_(
            Repository.owner_username == user.username,
            Repository.workspace_id.in_(
                workspace_ids,
            ),
        )
    )

    if workspace_id is not None:
        require_permission(
            db,
            workspace_id,
            user,
            "view",
        )

        query = query.filter(
            Repository.workspace_id == workspace_id,
        )

    return (
        query
        .order_by(
            Repository.created_at.desc()
        )
        .all()
    )


# ------------------------------------------------------------------
# SINGLE REPOSITORY
# ------------------------------------------------------------------

@router.get(
    "/{repository_id}",
    response_model=RepositoryResponse,
)
def get_repository(
    repository_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    repo = repository_is_accessible(
        db,
        repository_id,
        user,
    )

    if repo.workspace_id is not None:
        require_permission(
            db,
            repo.workspace_id,
            user,
            "view",
        )

    return repo



# ------------------------------------------------------------------
# DISCONNECT REPOSITORY
# ------------------------------------------------------------------

@router.delete(
    "/{repository_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def disconnect_repository(
    repository_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    repo = repository_is_accessible(
        db,
        repository_id,
        user,
    )

    if repo.workspace_id is not None:
        require_permission(
            db,
            repo.workspace_id,
            user,
            "manage_workspace",
        )

    active_job = (
        db.query(IndexJob)
        .filter(
            IndexJob.repository_id == repository_id,
            IndexJob.status.in_(["queued", "running"]),
        )
        .first()
    )

    if active_job:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Repository is currently indexing. Wait for indexing to finish before disconnecting it.",
        )

    db.query(IndexJob).filter(
        IndexJob.repository_id == repository_id,
    ).delete(synchronize_session=False)

    db.query(CodeChunk).filter(
        CodeChunk.repository_id == repository_id,
    ).delete(synchronize_session=False)

    db.delete(repo)
    db.commit()

# ------------------------------------------------------------------
# DASHBOARD
# ------------------------------------------------------------------

@router.get(
    "/{repository_id}/dashboard",
)
def repository_dashboard(
    repository_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    repo = repository_is_accessible(
        db,
        repository_id,
        user,
    )

    if repo.workspace_id is not None:
        require_permission(
            db,
            repo.workspace_id,
            user,
            "view",
        )

    total_chunks = (
        db.query(CodeChunk)
        .filter(
            CodeChunk.repository_id == repository_id,
        )
        .count()
    )

    embedded_chunks = (
        db.query(CodeChunk)
        .filter(
            CodeChunk.repository_id == repository_id,
            CodeChunk.embedding.isnot(None),
        )
        .count()
    )

    files_indexed = (
        db.query(CodeChunk.file_path)
        .filter(
            CodeChunk.repository_id == repository_id,
        )
        .distinct()
        .count()
    )

    jobs = (
        db.query(IndexJob)
        .filter(
            IndexJob.repository_id == repository_id,
        )
        .order_by(
            IndexJob.created_at.desc()
        )
        .limit(20)
        .all()
    )

    latest_job = jobs[0] if jobs else None

    try:
        needs_update = repository_needs_update(repo)
    except Exception:
        needs_update = True

    if repo.status == "error":
        health = "error"
    elif needs_update:
        health = "outdated"
    elif total_chunks == 0:
        health = "empty"
    elif embedded_chunks < total_chunks:
        health = "indexing"
    else:
        health = "healthy"

    return {
        "repository": {
            "id": repo.id,
            "name": repo.name,
            "url": repo.url,
            "branch": repo.branch,
            "status": repo.status,
            "last_indexed_commit": (
                repo.last_indexed_commit
            ),
            "created_at": repo.created_at,
            "workspace_id": repo.workspace_id,
        },
        "statistics": {
            "files_indexed": files_indexed,
            "total_chunks": total_chunks,
            "embedded_chunks": embedded_chunks,
            "embedding_status": (
                "complete"
                if (
                    total_chunks > 0
                    and embedded_chunks == total_chunks
                )
                else "partial"
                if embedded_chunks > 0
                else "not_started"
            ),
        },
        "git": {
            "last_indexed_commit": (
                repo.last_indexed_commit
            ),
            "needs_update": needs_update,
        },
        "health": {
            "status": health,
            "needs_update": needs_update,
            "index_ready": (
                total_chunks > 0
                and embedded_chunks == total_chunks
            ),
        },
        "latest_job": (
            IndexJobResponse
            .model_validate(latest_job)
            .model_dump()
            if latest_job
            else None
        ),
        "indexing_history": [
            IndexJobResponse
            .model_validate(job)
            .model_dump()
            for job in jobs
        ],
    }


# ------------------------------------------------------------------
# STATUS
# ------------------------------------------------------------------

@router.get(
    "/{repository_id}/status",
)
def repository_status(
    repository_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    repo = repository_is_accessible(
        db,
        repository_id,
        user,
    )

    if repo.workspace_id is not None:
        require_permission(
            db,
            repo.workspace_id,
            user,
            "view",
        )

    try:
        needs_update = repository_needs_update(repo)
    except Exception:
        needs_update = True

    total_chunks = (
        db.query(CodeChunk)
        .filter(
            CodeChunk.repository_id == repository_id,
        )
        .count()
    )

    embedded_chunks = (
        db.query(CodeChunk)
        .filter(
            CodeChunk.repository_id == repository_id,
            CodeChunk.embedding.isnot(None),
        )
        .count()
    )

    files_indexed = (
        db.query(CodeChunk.file_path)
        .filter(
            CodeChunk.repository_id == repository_id,
        )
        .distinct()
        .count()
    )

    latest_job = (
        db.query(IndexJob)
        .filter(
            IndexJob.repository_id == repository_id,
        )
        .order_by(
            IndexJob.created_at.desc()
        )
        .first()
    )

    queued = (
        db.query(IndexJob)
        .filter(
            IndexJob.repository_id == repository_id,
            IndexJob.status.in_(
                ["queued", "running"],
            ),
        )
        .order_by(
            IndexJob.created_at.desc()
        )
        .first()
    )

    return {
        "repository_id": repository_id,
        "status": repo.status,
        "files_indexed": files_indexed,
        "total_chunks": total_chunks,
        "embedded_chunks": embedded_chunks,
        "embedding_status": (
            "complete"
            if (
                total_chunks > 0
                and embedded_chunks == total_chunks
            )
            else "partial"
            if embedded_chunks > 0
            else "not_started"
        ),
        "last_indexed_commit": (
            repo.last_indexed_commit
        ),
        "needs_update": needs_update,
        "job": (
            IndexJobResponse
            .model_validate(queued)
            .model_dump()
            if queued
            else None
        ),
        "last_index_job": (
            IndexJobResponse
            .model_validate(latest_job)
            .model_dump()
            if latest_job
            else None
        ),
    }


# ------------------------------------------------------------------
# FILE TREE
# ------------------------------------------------------------------

@router.get(
    "/{repository_id}/files",
)
def repository_files(
    repository_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    repo = repository_is_accessible(
        db,
        repository_id,
        user,
    )

    if repo.workspace_id is not None:
        require_permission(
            db,
            repo.workspace_id,
            user,
            "view",
        )

    paths = (
        db.query(CodeChunk.file_path)
        .filter(
            CodeChunk.repository_id == repository_id,
        )
        .distinct()
        .order_by(
            CodeChunk.file_path
        )
        .all()
    )

    files = [row[0] for row in paths]

    return {
        "repository_id": repository_id,
        "files": files,
        "count": len(files),
    }


# ------------------------------------------------------------------
# FILE SEARCH
# ------------------------------------------------------------------

@router.get(
    "/{repository_id}/files/search",
)
def search_repository_files(
    repository_id: int,
    q: str = Query(
        ...,
        min_length=1,
        max_length=200,
    ),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    repo = repository_is_accessible(
        db,
        repository_id,
        user,
    )

    if repo.workspace_id is not None:
        require_permission(
            db,
            repo.workspace_id,
            user,
            "view",
        )

    pattern = f"%{q}%"

    rows = (
        db.query(CodeChunk.file_path)
        .filter(
            CodeChunk.repository_id == repository_id,
            CodeChunk.file_path.ilike(pattern),
        )
        .distinct()
        .order_by(
            CodeChunk.file_path
        )
        .limit(100)
        .all()
    )

    return {
        "query": q,
        "files": [
            row[0]
            for row in rows
        ],
    }


# ------------------------------------------------------------------
# EXACT FILE SOURCE
# ------------------------------------------------------------------

@router.get(
    "/{repository_id}/files/source",
)
def get_file_source(
    repository_id: int,
    path: str = Query(
        ...,
        min_length=1,
    ),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    repo = repository_is_accessible(
        db,
        repository_id,
        user,
    )

    if repo.workspace_id is not None:
        require_permission(
            db,
            repo.workspace_id,
            user,
            "view",
        )

    if not repo.local_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository has not been cloned yet.",
        )

    root = Path(repo.local_path).resolve()
    requested = (root / path).resolve()

    if (
        root not in requested.parents
        and requested != root
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file path.",
        )

    if not requested.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found.",
        )

    if not requested.is_file():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Path is not a file.",
        )

    try:
        content = requested.read_text(
            encoding="utf-8",
            errors="replace",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to read source file.",
        ) from exc

    lines = content.splitlines()

    return {
        "repository_id": repository_id,
        "file_path": path,
        "total_lines": len(lines),
        "content": content,
    }


# ------------------------------------------------------------------
# EXACT LINE RANGE
# ------------------------------------------------------------------

@router.get(
    "/{repository_id}/files/source/range",
)
def get_source_range(
    repository_id: int,
    path: str = Query(
        ...,
        min_length=1,
    ),
    start_line: int = Query(
        ...,
        ge=1,
    ),
    end_line: int = Query(
        ...,
        ge=1,
    ),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    if end_line < start_line:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "end_line must be greater than "
                "or equal to start_line."
            ),
        )

    repo = repository_is_accessible(
        db,
        repository_id,
        user,
    )

    if repo.workspace_id is not None:
        require_permission(
            db,
            repo.workspace_id,
            user,
            "view",
        )

    if not repo.local_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository has not been cloned yet.",
        )

    root = Path(repo.local_path).resolve()
    requested = (root / path).resolve()

    if (
        root not in requested.parents
        and requested != root
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file path.",
        )

    if (
        not requested.exists()
        or not requested.is_file()
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found.",
        )

    try:
        lines = requested.read_text(
            encoding="utf-8",
            errors="replace",
        ).splitlines()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to read source file.",
        ) from exc

    if start_line > len(lines):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Start line is outside the file.",
        )

    end_line = min(
        end_line,
        len(lines),
    )

    selected = lines[
        start_line - 1:end_line
    ]

    return {
        "repository_id": repository_id,
        "file_path": path,
        "start_line": start_line,
        "end_line": end_line,
        "content": "\n".join(selected),
    }


# ------------------------------------------------------------------
# INDEX
# ------------------------------------------------------------------

@router.post(
    "/{repository_id}/index",
    response_model=IndexJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def enqueue_index(
    repository_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    repo = repository_is_accessible(
        db,
        repository_id,
        user,
    )

    if repo.workspace_id is not None:
        require_permission(
            db,
            repo.workspace_id,
            user,
            "index_repository",
        )
    db.execute(
    text(
        "SELECT pg_advisory_xact_lock(:repository_id)"
    ),
    {"repository_id": repository_id},
)
    active = (
        db.query(IndexJob)
        .filter(
            IndexJob.repository_id == repository_id,
            IndexJob.status.in_(
                ["queued", "running"],
            ),
        )
        .first()
    )

    if active:
        return active

    job = IndexJob(
        repository_id=repository_id,
        stage="Queued",
    )

    db.add(job)

    repo.status = "indexing"

    db.commit()
    db.refresh(job)

    return job


# ------------------------------------------------------------------
# INDEX JOB
# ------------------------------------------------------------------

@router.get(
    "/{repository_id}/jobs/{job_id}",
    response_model=IndexJobResponse,
)
def get_index_job(
    repository_id: int,
    job_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    repo = repository_is_accessible(
        db,
        repository_id,
        user,
    )

    if repo.workspace_id is not None:
        require_permission(
            db,
            repo.workspace_id,
            user,
            "view",
        )

    job = db.get(
        IndexJob,
        job_id,
    )

    if (
        not job
        or job.repository_id != repo.id
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Index job not found.",
        )

    return job


# ------------------------------------------------------------------
# GIT STATUS
# ------------------------------------------------------------------

@router.get(
    "/{repository_id}/git/status",
)
def git_status(
    repository_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    repo = repository_is_accessible(
        db,
        repository_id,
        user,
    )

    if repo.workspace_id is not None:
        require_permission(
            db,
            repo.workspace_id,
            user,
            "view",
        )

    if not repo.local_path:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Repository has not been indexed yet.",
        )

    try:
        remote_commit = current_remote_commit(
            repo.local_path,
            repo.branch,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "Unable to check remote repository: "
                f"{exc}"
            ),
        ) from exc

    return {
        "repository_id": repo.id,
        "branch": repo.branch,
        "last_indexed_commit": (
            repo.last_indexed_commit
        ),
        "remote_commit": remote_commit,
        "needs_update": (
            repo.last_indexed_commit
            != remote_commit
        ),
    }


# ------------------------------------------------------------------
# GIT BRANCH COMPARISON
# ------------------------------------------------------------------

@router.get(
    "/{repository_id}/git/compare",
    response_model=GitCompareResponse,
)
def git_compare(
    repository_id: int,
    base: str = Query(
        ...,
        min_length=1,
        max_length=255,
    ),
    target: str = Query(
        ...,
        min_length=1,
        max_length=255,
    ),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    repo = repository_is_accessible(
        db,
        repository_id,
        user,
    )

    if repo.workspace_id is not None:
        require_permission(
            db,
            repo.workspace_id,
            user,
            "view",
        )

    if not repo.local_path:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Repository has not been indexed yet.",
        )

    try:
        result = compare_refs(
            repo.local_path,
            base,
            target,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Unable to compare Git refs: "
                f"{exc}"
            ),
        ) from exc

    return result


# ------------------------------------------------------------------
# GIT COMMIT
# ------------------------------------------------------------------

@router.get(
    "/{repository_id}/git/commit/{commit_sha}",
    response_model=GitCommitResponse,
)
def get_commit(
    repository_id: int,
    commit_sha: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    repo = repository_is_accessible(
        db,
        repository_id,
        user,
    )

    if repo.workspace_id is not None:
        require_permission(
            db,
            repo.workspace_id,
            user,
            "view",
        )

    if not repo.local_path:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Repository has not been indexed yet.",
        )

    if not re.fullmatch(
        r"[0-9a-fA-F]{7,64}",
        commit_sha,
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid commit SHA.",
        )

    try:
        return commit_info(
            repo.local_path,
            commit_sha,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Commit not found: {commit_sha}",
        ) from exc


# ------------------------------------------------------------------
# PULL REQUEST ANALYSIS
# ------------------------------------------------------------------

@router.post(
    "/{repository_id}/git/pr/{pr_number}/analyze",
)
def analyze_pull_request_route(
    repository_id: int,
    pr_number: int,
    payload: PullRequestAnalyzeRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    repo = repository_is_accessible(
        db,
        repository_id,
        user,
    )

    if repo.workspace_id is not None:
        require_permission(
            db,
            repo.workspace_id,
            user,
            "ask_ai",
        )

    if not repo.local_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Repository must be indexed before "
                "analyzing a PR."
            ),
        )

    try:
        return analyze_pull_request(
            repository_path=repo.local_path,
            pr_number=pr_number,
            base_branch=(
                payload.base_branch.strip()
                or repo.branch
            ),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to analyze pull request.",
        ) from exc


# ------------------------------------------------------------------
# ARCHITECTURE INTELLIGENCE
# ------------------------------------------------------------------

@router.get(
    "/{repository_id}/architecture",
)
def repository_architecture(
    repository_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    repo = repository_is_accessible(
        db,
        repository_id,
        user,
    )

    if repo.workspace_id is not None:
        require_permission(
            db,
            repo.workspace_id,
            user,
            "view",
        )

    if not repo.local_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Repository has not been indexed yet.",
        )

    if repo.status != "indexed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Repository index is not ready.",
        )

    try:
        return architecture_report(
            repo.local_path,
        )
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Unable to analyze repository "
                f"architecture: {exc}"
            ),
        ) from exc


# ------------------------------------------------------------------
# CODE QUALITY
# ------------------------------------------------------------------

@router.get(
    "/{repository_id}/quality",
)
def repository_quality(
    repository_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    repo = repository_is_accessible(
        db,
        repository_id,
        user,
    )

    if repo.workspace_id is not None:
        require_permission(
            db,
            repo.workspace_id,
            user,
            "view",
        )

    if not repo.local_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Repository has not been indexed locally.",
        )

    try:
        return {
            "repository": {
                "id": repo.id,
                "name": repo.name,
                "branch": repo.branch,
                "last_indexed_commit": (
                    repo.last_indexed_commit
                ),
                "workspace_id": repo.workspace_id,
            },
            "analysis": analyze_repository(
                repo.local_path,
            ),
        }
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Unable to analyze repository "
                f"quality: {exc}"
            ),
        ) from exc