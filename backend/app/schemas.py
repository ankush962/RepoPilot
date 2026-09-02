from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class RepositoryCreate(BaseModel):
    url: HttpUrl
    branch: str = Field(default="main", min_length=1, max_length=255)


class RepositoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    url: str
    branch: str
    status: str
    created_at: datetime


class ChatRequest(BaseModel):
    repository_id: int = Field(gt=0)
    message: str = Field(min_length=1, max_length=4000)
    commit_sha: str | None = Field(
        default=None,
        min_length=7,
        max_length=64,
    )


class Source(BaseModel):
    file_path: str
    start_line: int
    end_line: int
    content: str
    similarity: float | None = None


class Metrics(BaseModel):
    sources: int
    average_similarity: float
    top_similarity: float
    latency_seconds: float
    grounding: str


class ChatResponse(BaseModel):
    answer: str
    sources: list[Source]
    metrics: Metrics


class IndexJobResponse(BaseModel):
    id: int
    repository_id: int
    status: str
    progress: int
    stage: str
    attempts: int
    error: str | None = None
    result_chunks: int = 0
    result_vectors: int = 0
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class GitCommit(BaseModel):
    sha: str
    short_sha: str
    message: str
    author: str | None = None
    email: str | None = None
    committed_at: str | None = None


class GitChangedFile(BaseModel):
    change_type: str
    old_path: str | None = None
    new_path: str | None = None


class GitCompareResponse(BaseModel):
    base: str
    target: str
    base_commit: str
    target_commit: str
    files: list[GitChangedFile]
    commits: list[GitCommit]
    files_changed: int
    commits_count: int


class GitCommitResponse(BaseModel):
    sha: str
    short_sha: str
    message: str
    author: str | None = None
    email: str | None = None
    committed_at: str | None = None
    files: list[GitChangedFile]

class PullRequestAnalyzeRequest(BaseModel):
    base_branch: str = Field(
        default="main",
        min_length=1,
        max_length=255,
    )

class WorkspaceCreate(BaseModel):
    name: str = Field(
        min_length=1,
        max_length=255,
    )


class WorkspaceResponse(BaseModel):
    id: int
    name: str
    slug: str
    created_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
    )


class WorkspaceMemberResponse(BaseModel):
    user_id: int
    username: str
    role: str


class WorkspaceMemberCreate(BaseModel):
    username: str = Field(
        min_length=1,
        max_length=255,
    )

    role: str = Field(
        default="viewer",
        pattern="^(owner|admin|developer|viewer)$",
    )


class WorkspaceRoleUpdate(BaseModel):
    role: str = Field(
        pattern="^(admin|developer|viewer)$",
    )

class RegisterRequest(BaseModel):
    username: str = Field(
        min_length=3,
        max_length=255,
    )
    password: str = Field(
        min_length=8,
        max_length=255,
    )


class LoginRequest(BaseModel):
    username: str
    password: str




class ConversationMessageCreate(BaseModel):
    content: str = Field(
        min_length=1,
        max_length=20000,
    )




class ConversationMessageResponse(BaseModel):
    id: int
    conversation_id: int
    role: str
    content: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ConversationCreate(BaseModel):
    repository_id: int = Field(gt=0)
    title: str = Field(
        default="New conversation",
        min_length=1,
        max_length=255,
    )


class ConversationUpdate(BaseModel):
    title: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
    )


class ConversationResponse(BaseModel):
    id: int
    repository_id: int
    owner_username: str
    title: str
    created_at: datetime
    updated_at: datetime
    messages: list[ConversationMessageResponse] = []

    model_config = ConfigDict(from_attributes=True)
