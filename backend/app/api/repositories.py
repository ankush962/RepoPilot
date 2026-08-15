from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Repository, CodeChunk
from app.schemas import RepositoryCreate, RepositoryResponse
from app.services.ingestion import repository_name, index_repository
from app.services.vector_store import upsert_chunks

router = APIRouter(prefix="/repositories", tags=["repositories"])

@router.post("", response_model=RepositoryResponse)
def create_repository(payload: RepositoryCreate, db: Session = Depends(get_db)):
    url = str(payload.url); existing = db.query(Repository).filter(Repository.url == url).first()
    if existing: return existing
    repo = Repository(name=repository_name(url), url=url, branch=payload.branch)
    db.add(repo); db.commit(); db.refresh(repo); return repo

@router.get("", response_model=list[RepositoryResponse])
def list_repositories(db: Session = Depends(get_db)): return db.query(Repository).order_by(Repository.created_at.desc()).all()

@router.get("/{repository_id}", response_model=RepositoryResponse)
def get_repository(repository_id: int, db: Session = Depends(get_db)):
    repo = db.get(Repository, repository_id)
    if not repo: raise HTTPException(404, "Repository not found")
    return repo

@router.post("/{repository_id}/index")
def index(repository_id: int, db: Session = Depends(get_db)):
    repo = db.get(Repository, repository_id)
    if not repo: raise HTTPException(404, "Repository not found")
    try:
        count = index_repository(db, repo)
        chunks = db.query(CodeChunk).filter_by(repository_id=repository_id).all()
        if chunks: upsert_chunks(chunks)
        return {"status":"indexed", "chunks":count}
    except Exception as exc:
        repo.status = "error"; db.commit(); raise HTTPException(500, str(exc))
