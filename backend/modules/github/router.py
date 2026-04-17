import json

from fastapi import APIRouter, Depends, Header, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps.auth import get_current_user
from backend.api.deps.db import get_db
from backend.core.config import settings
from backend.modules.github.schemas import (
    GithubAppInstallResponse,
    GithubCommentRequest,
    GithubConnectionCreate,
    GithubConnectionResponse,
    GithubIssueImportRequest,
    GithubIssueLinkResponse,
    GithubRepositoryResponse,
    GithubSyncEventResponse,
    GithubWebhookResponse,
)
from backend.modules.identity_access.models import User
from backend.modules.orchestration.schemas import ApprovalResponse, TaskResponse
from backend.modules.orchestration.service import OrchestrationService

router = APIRouter()
public_router = APIRouter()


def _github_connection(item) -> GithubConnectionResponse:
    metadata = item.metadata_json or {}
    return GithubConnectionResponse(
        id=item.id,
        name=item.name,
        api_url=item.api_url,
        connection_mode=metadata.get("connection_mode", "token"),
        installation_id=metadata.get("installation_id"),
        organization_login=metadata.get("account_login"),
        token_hint=item.token_hint,
        account_login=item.account_login,
        is_active=bool(item.is_active),
        metadata=metadata,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _github_repository(item) -> GithubRepositoryResponse:
    return GithubRepositoryResponse(
        id=item.id,
        connection_id=item.connection_id,
        project_id=item.project_id,
        owner_name=item.owner_name,
        repo_name=item.repo_name,
        full_name=item.full_name,
        default_branch=item.default_branch,
        repo_url=item.repo_url,
        is_active=bool(item.is_active),
        metadata=item.metadata_json,
        last_synced_at=item.last_synced_at,
        created_at=item.created_at,
    )


def _github_issue_link(item) -> GithubIssueLinkResponse:
    return GithubIssueLinkResponse(
        id=item.id,
        repository_id=item.repository_id,
        task_id=item.task_id,
        issue_number=item.issue_number,
        title=item.title,
        body=item.body,
        state=item.state,
        labels=item.labels_json,
        assignee_login=item.assignee_login,
        issue_url=item.issue_url,
        sync_status=item.sync_status,
        last_comment_posted_at=item.last_comment_posted_at,
        last_synced_at=item.last_synced_at,
        last_error=item.last_error,
        metadata=item.metadata_json,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _github_sync_event(item) -> GithubSyncEventResponse:
    return GithubSyncEventResponse(
        id=item.id,
        repository_id=item.repository_id,
        issue_link_id=item.issue_link_id,
        action=item.action,
        status=item.status,
        detail=item.detail,
        payload=item.payload_json,
        created_at=item.created_at,
    )


def _approval(item) -> ApprovalResponse:
    return ApprovalResponse(
        id=item.id,
        project_id=item.project_id,
        task_id=item.task_id,
        run_id=item.run_id,
        approval_type=item.approval_type,
        status=item.status,
        title=item.title,
        summary=item.summary,
        detail=item.detail,
        payload=item.payload_json,
        requested_by_user_id=item.requested_by_user_id,
        approved_by_user_id=item.approved_by_user_id,
        decision_reason=item.decision_reason,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _task(item, github_summary: dict | None = None) -> TaskResponse:
    gh_num = gh_url = gh_repo = None
    if github_summary:
        raw_n = github_summary.get("issue_number")
        gh_num = int(raw_n) if raw_n is not None else None
        u = github_summary.get("issue_url")
        gh_url = str(u) if u else None
        rfn = github_summary.get("repository_full_name")
        gh_repo = str(rfn) if rfn else None
    return TaskResponse(
        id=item.id,
        project_id=item.project_id,
        created_by_user_id=item.created_by_user_id,
        assigned_agent_id=item.assigned_agent_id,
        reviewer_agent_id=item.reviewer_agent_id,
        github_issue_link_id=item.github_issue_link_id,
        github_issue_number=gh_num,
        github_issue_url=gh_url,
        github_repository_full_name=gh_repo,
        parent_task_id=item.parent_task_id,
        title=item.title,
        description=item.description,
        source=item.source,
        task_type=item.task_type,
        priority=item.priority,
        status=item.status,
        acceptance_criteria=item.acceptance_criteria,
        due_date=item.due_date,
        response_sla_hours=getattr(item, "response_sla_hours", None),
        labels=item.labels_json,
        result_summary=item.result_summary,
        result_payload=item.result_payload_json,
        position=item.position,
        metadata=item.metadata_json,
        dependency_ids=[],
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


async def _tasks_to_responses(
    service: OrchestrationService,
    tasks: list,
) -> list[TaskResponse]:
    link_ids = [t.github_issue_link_id for t in tasks if t.github_issue_link_id]
    summaries = await service.github_issue_summaries_for_link_ids(link_ids)
    result: list[TaskResponse] = []
    for task in tasks:
        gh = summaries.get(task.github_issue_link_id) if task.github_issue_link_id else None
        result.append(_task(task, gh))
    return result


@router.get("/github/connections", response_model=list[GithubConnectionResponse])
async def list_github_connections(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = OrchestrationService(db)
    return [_github_connection(item) for item in await service.list_github_connections(current_user)]


@router.get("/github/app/install-url", response_model=GithubAppInstallResponse)
async def github_app_install_url(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return GithubAppInstallResponse(
        install_url=await OrchestrationService(db).build_github_app_install_url(current_user)
    )


@router.get("/github/app/callback")
async def github_app_callback(
    installation_id: int,
    setup_action: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    connection = await OrchestrationService(db).finalize_github_app_installation(
        current_user,
        installation_id=installation_id,
        setup_action=setup_action,
    )
    return RedirectResponse(
        url=f"{settings.FRONTEND_URL.rstrip('/')}/admin/settings?tab=github&connection_id={connection.id}",
        status_code=302,
    )


@router.post("/github/connections", response_model=GithubConnectionResponse, status_code=201)
async def create_github_connection(
    payload: GithubConnectionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = OrchestrationService(db)
    return _github_connection(await service.create_github_connection(current_user, payload.model_dump()))


@router.post("/github/connections/{connection_id}/sync-repos", response_model=list[GithubRepositoryResponse])
async def sync_github_repositories(
    connection_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = OrchestrationService(db)
    return [_github_repository(item) for item in await service.sync_github_repositories(current_user, connection_id)]


@router.get("/github/repositories", response_model=list[GithubRepositoryResponse])
async def list_github_repositories(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = OrchestrationService(db)
    return [_github_repository(item) for item in await service.list_github_repositories(current_user)]


@router.post("/github/import-issues", response_model=list[TaskResponse])
async def import_github_issues(
    payload: GithubIssueImportRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = OrchestrationService(db)
    tasks = await service.import_github_issues(current_user, payload.model_dump())
    return await _tasks_to_responses(service, tasks)


@router.get("/github/issues", response_model=list[GithubIssueLinkResponse])
async def list_github_issue_links(
    project_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = OrchestrationService(db)
    return [_github_issue_link(item) for item in await service.list_github_issue_links(current_user, project_id)]


@router.get("/github/sync-events", response_model=list[GithubSyncEventResponse])
async def list_github_sync_events(
    project_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = OrchestrationService(db)
    return [_github_sync_event(item) for item in await service.list_github_sync_events(current_user, project_id)]


@router.post("/github/issues/{issue_link_id}/comment", response_model=ApprovalResponse, status_code=201)
async def request_github_comment(
    issue_link_id: str,
    payload: GithubCommentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = OrchestrationService(db)
    approval = await service.create_github_comment_approval(
        current_user,
        issue_link_id,
        payload.body,
        payload.close_issue,
    )
    return _approval(approval)


@public_router.post("/webhooks/github", response_model=GithubWebhookResponse)
async def github_webhook(
    request: Request,
    x_github_event: str = Header(default=""),
    x_hub_signature_256: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    body = await request.body()
    service = OrchestrationService(db)
    if not settings.GITHUB_APP_WEBHOOK_SECRET:
        return Response(status_code=503, content="GitHub webhook secret is not configured")
    if not service.validate_github_webhook_signature(body, x_hub_signature_256):
        return Response(status_code=401)
    payload = json.loads(body.decode("utf-8") or "{}")
    sync_event_id = await service.record_github_webhook_event(x_github_event, payload)
    from backend.workers.orchestration import queue_github_webhook_event

    queue_github_webhook_event(sync_event_id)
    return GithubWebhookResponse(accepted=True, sync_event_id=sync_event_id)
