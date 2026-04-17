from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from backend.core.schemas import RequestModel


class GithubConnectionCreate(RequestModel):
    name: str = Field(min_length=2, max_length=255)
    api_url: str = "https://api.github.com"
    token: str | None = None


class GithubConnectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    api_url: str
    connection_mode: str = "token"
    installation_id: int | None = None
    organization_login: str | None = None
    token_hint: str | None
    account_login: str | None
    is_active: bool
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class GithubRepositoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    connection_id: str
    project_id: str | None
    owner_name: str
    repo_name: str
    full_name: str
    default_branch: str | None
    repo_url: str | None
    is_active: bool
    metadata: dict[str, Any]
    last_synced_at: datetime | None
    created_at: datetime


class GithubIssueImportRequest(RequestModel):
    project_id: str
    repository_id: str
    issue_numbers: list[int] = Field(default_factory=list)
    auto_assign_agent_id: str | None = None


class GithubIssueLinkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    repository_id: str
    task_id: str | None
    issue_number: int
    title: str
    body: str | None
    state: str
    labels: list[str]
    assignee_login: str | None
    issue_url: str | None
    sync_status: str
    last_comment_posted_at: datetime | None
    last_synced_at: datetime | None
    last_error: str | None
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class GithubSyncEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    repository_id: str | None
    issue_link_id: str | None
    action: str
    status: str
    detail: str | None
    payload: dict[str, Any]
    created_at: datetime


class GithubCommentRequest(RequestModel):
    body: str = Field(min_length=1)
    close_issue: bool = False


class GithubAppInstallResponse(BaseModel):
    install_url: str


class GithubWebhookResponse(BaseModel):
    accepted: bool = True
    sync_event_id: str | None = None
