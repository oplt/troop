"""Department management endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps.auth import get_authenticated_user
from backend.db.session import get_db
from backend.modules.identity_access.models import User
from backend.modules.workforce.schemas import (
    DepartmentCreate,
    DepartmentResponse,
    DepartmentUpdate,
)
from backend.modules.workforce.services.department_service import DepartmentService

router = APIRouter(prefix="/departments")


@router.get("", response_model=list[DepartmentResponse])
async def list_departments(
    company_id: str,
    include_archived: bool = False,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> list[DepartmentResponse]:
    """List departments for a company."""
    service = DepartmentService(db)
    departments = await service.list(user.id, company_id, include_archived=include_archived)
    return [DepartmentResponse.model_validate(dept) for dept in departments]


@router.post("", response_model=DepartmentResponse, status_code=201)
async def create_department(
    payload: DepartmentCreate,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> DepartmentResponse:
    """Create a new department."""
    service = DepartmentService(db)
    dept = await service.create(
        owner_id=user.id,
        company_id=payload.company_id,
        name=payload.name,
        slug=payload.slug,
        description=payload.description,
        parent_department_id=payload.parent_department_id,
        default_knowledge_policy_json=payload.default_knowledge_policy,
        default_tool_policy_json=payload.default_tool_policy,
        default_model_policy_json=payload.default_model_policy,
        default_approval_policy_json=payload.default_approval_policy,
        budget_policy_json=payload.budget_policy,
        metadata_json=payload.metadata,
    )
    return DepartmentResponse.model_validate(dept)


@router.patch("/{department_id}", response_model=DepartmentResponse)
async def update_department(
    department_id: str,
    payload: DepartmentUpdate,
    company_id: str | None = None,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> DepartmentResponse:
    """Update a department (company_id optional — resolved from ownership)."""
    service = DepartmentService(db)
    kwargs = {}
    if payload.name is not None:
        kwargs["name"] = payload.name
    if payload.description is not None:
        kwargs["description"] = payload.description
    if payload.parent_department_id is not None:
        kwargs["parent_department_id"] = payload.parent_department_id
    if payload.default_knowledge_policy is not None:
        kwargs["default_knowledge_policy_json"] = payload.default_knowledge_policy
    if payload.default_tool_policy is not None:
        kwargs["default_tool_policy_json"] = payload.default_tool_policy
    if payload.default_model_policy is not None:
        kwargs["default_model_policy_json"] = payload.default_model_policy
    if payload.default_approval_policy is not None:
        kwargs["default_approval_policy_json"] = payload.default_approval_policy
    if payload.budget_policy is not None:
        kwargs["budget_policy_json"] = payload.budget_policy
    if payload.metadata is not None:
        kwargs["metadata_json"] = payload.metadata
    if payload.is_archived is not None:
        kwargs["is_archived"] = payload.is_archived

    if company_id:
        dept = await service.update(user.id, company_id, department_id, **kwargs)
    else:
        dept = await service.update_for_owner(user.id, department_id, **kwargs)
    return DepartmentResponse.model_validate(dept)


@router.post("/{department_id}/archive", status_code=204)
async def archive_department(
    department_id: str,
    company_id: str | None = None,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Archive a department (company_id optional — resolved from ownership)."""
    service = DepartmentService(db)
    if company_id:
        await service.update(user.id, company_id, department_id, is_archived=True)
    else:
        await service.update_for_owner(user.id, department_id, is_archived=True)
