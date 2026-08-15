from datetime import datetime
from pydantic import BaseModel, HttpUrl, ConfigDict

class RepositoryCreate(BaseModel):
    url: HttpUrl
    branch: str = "main"

class RepositoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    url: str
    branch: str
    status: str
    created_at: datetime

class ChatRequest(BaseModel):
    repository_id: int
    message: str

class Source(BaseModel):
    file_path: str
    start_line: int
    end_line: int
    content: str

class ChatResponse(BaseModel):
    answer: str
    sources: list[Source]
