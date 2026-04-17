from datetime import datetime
from uuid import uuid4

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base
from backend.modules.orchestration.model_utils import utcnow


class GithubConnection(Base):
    __tablename__ = "github_connections"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    api_url: Mapped[str] = mapped_column(String(500), default="https://api.github.com")
    encrypted_token: Mapped[str] = mapped_column(Text)
    token_hint: Mapped[str | None] = mapped_column(String(32), nullable=True)
    account_login: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class GithubRepository(Base):
    __tablename__ = "github_repositories"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    connection_id: Mapped[str] = mapped_column(
        ForeignKey("github_connections.id", ondelete="CASCADE"),
        index=True,
    )
    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("orchestrator_projects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    owner_name: Mapped[str] = mapped_column(String(255))
    repo_name: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(255), index=True)
    default_branch: Mapped[str | None] = mapped_column(String(255), nullable=True)
    repo_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class GithubIssueLink(Base):
    __tablename__ = "github_issue_links"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    repository_id: Mapped[str] = mapped_column(
        ForeignKey("github_repositories.id", ondelete="CASCADE"),
        index=True,
    )
    task_id: Mapped[str | None] = mapped_column(
        ForeignKey("orchestrator_tasks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    issue_number: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(255))
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    state: Mapped[str] = mapped_column(String(32), default="open")
    labels_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    assignee_login: Mapped[str | None] = mapped_column(String(255), nullable=True)
    issue_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    sync_status: Mapped[str] = mapped_column(String(32), default="synced")
    last_comment_posted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class GithubSyncEvent(Base):
    __tablename__ = "github_sync_events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    repository_id: Mapped[str | None] = mapped_column(
        ForeignKey("github_repositories.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    issue_link_id: Mapped[str | None] = mapped_column(
        ForeignKey("github_issue_links.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    action: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="completed")
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
