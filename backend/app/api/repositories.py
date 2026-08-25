from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Repository, CodeChunk

from app.schemas import (
    RepositoryCreate,
    RepositoryResponse,
)

from app.services.ingestion import (
    repository_name,
    index_repository,
    repository_needs_update,
)

from app.services.vector_store import (
    upsert_chunks,
)


router = APIRouter(
    prefix="/repositories",
    tags=["repositories"],
)


def vectors_need_rebuild(
    db: Session,
    repository_id: int,
) -> bool:

    result = db.execute(
        text(
            """
            SELECT
                COUNT(*) AS total,
                COUNT(embedding) AS embedded
            FROM code_chunks
            WHERE repository_id = :repository_id
            """
        ),
        {
            "repository_id": repository_id,
        },
    ).first()

    if not result:
        return True

    total = int(result.total or 0)
    embedded = int(result.embedded or 0)

    return total == 0 or embedded < total


@router.post(
    "",
    response_model=RepositoryResponse,
)
def create_repository(
    payload: RepositoryCreate,
    db: Session = Depends(get_db),
):

    url = str(payload.url)

    existing = (
        db.query(Repository)
        .filter(
            Repository.url == url
        )
        .first()
    )

    if existing:
        return existing

    repo = Repository(
        name=repository_name(url),
        url=url,
        branch=payload.branch,
    )

    db.add(repo)
    db.commit()
    db.refresh(repo)

    return repo


@router.get(
    "",
    response_model=list[RepositoryResponse],
)
def list_repositories(
    db: Session = Depends(get_db),
):

    return (
        db.query(Repository)
        .order_by(
            Repository.created_at.desc()
        )
        .all()
    )


@router.get(
    "/{repository_id}",
    response_model=RepositoryResponse,
)
def get_repository(
    repository_id: int,
    db: Session = Depends(get_db),
):

    repo = db.get(
        Repository,
        repository_id,
    )

    if not repo:

        raise HTTPException(
            404,
            "Repository not found",
        )

    return repo


@router.get(
    "/{repository_id}/status",
)
def repository_status(
    repository_id: int,
    db: Session = Depends(get_db),
):

    repo = db.get(
        Repository,
        repository_id,
    )

    if not repo:

        raise HTTPException(
            404,
            "Repository not found",
        )

    try:

        needs_update = (
            repository_needs_update(
                repo
            )
        )

    except Exception:

        needs_update = True

    return {
        "repository_id": repository_id,
        "status": repo.status,
        "last_indexed_commit": (
            repo.last_indexed_commit
        ),
        "needs_update": needs_update,
    }


@router.post(
    "/{repository_id}/index",
)
def index(
    repository_id: int,
    db: Session = Depends(get_db),
):

    repo = db.get(
        Repository,
        repository_id,
    )

    if not repo:

        raise HTTPException(
            404,
            "Repository not found",
        )

    try:

        count = index_repository(
            db,
            repo,
        )

        needs_vectors = vectors_need_rebuild(
            db,
            repository_id,
        )

        # Nothing changed and vectors are healthy.
        if count == 0 and not needs_vectors:

            return {
                "status": "up_to_date",
                "chunks": 0,
                "vectors": 0,
                "commit": repo.last_indexed_commit,
            }

        chunks = (
            db.query(CodeChunk)
            .filter_by(
                repository_id=repository_id
            )
            .all()
        )

        vector_count = 0

        if chunks:

            vector_count = upsert_chunks(
                chunks
            )

        return {
            "status": "indexed",
            "chunks": count,
            "vectors": vector_count,
            "commit": repo.last_indexed_commit,
        }

    except Exception as exc:

        repo.status = "error"

        db.commit()

        raise HTTPException(
            500,
            str(exc),
        )