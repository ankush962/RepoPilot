from pathlib import Path
from git import Repo
from sqlalchemy.orm import Session
from app.config import settings
from app.models import Repository, CodeChunk
from app.services.chunker import iter_code_files, chunk_file

def repository_name(url: str) -> str:
    value = url.rstrip("/").split("/")[-1]
    return value[:-4] if value.endswith(".git") else value

def index_repository(db: Session, repository: Repository):
    workspace = Path(settings.workspace_dir).resolve(); workspace.mkdir(parents=True, exist_ok=True)
    destination = workspace / f"repo_{repository.id}"
    if destination.exists():
        repo = Repo(destination); repo.git.fetch("--all"); repo.git.checkout(repository.branch); repo.git.pull()
    else:
        Repo.clone_from(repository.url, destination, branch=repository.branch)
    repository.local_path = str(destination); repository.status = "cloned"
    db.query(CodeChunk).filter(CodeChunk.repository_id == repository.id).delete()
    count = 0
    for file_path in iter_code_files(destination):
        for chunk in chunk_file(file_path):
            db.add(CodeChunk(repository_id=repository.id, file_path=str(file_path.relative_to(destination)), start_line=chunk["start_line"], end_line=chunk["end_line"], content=chunk["content"]))
            count += 1
    repository.status = "indexed"; db.commit()
    return count
