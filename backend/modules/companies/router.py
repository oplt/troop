from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps.auth import get_authenticated_user
from backend.db.session import get_db
from backend.modules.companies.schemas import (
    CompanyCreate,
    CompanyResponse,
    CompanyUpdate,
)
from backend.modules.companies.service import CompanyService
from backend.modules.identity_access.models import User

router = APIRouter()


@router.get("", response_model=list[CompanyResponse])
async def list_companies(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_authenticated_user),
):
    service = CompanyService(db)
    items = await service.list_for(current_user.id)
    return [CompanyResponse.model_validate(item) for item in items]


@router.post("", response_model=CompanyResponse, status_code=201)
async def create_company(
    payload: CompanyCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_authenticated_user),
):
    service = CompanyService(db)
    item = await service.create(
        current_user.id,
        name=payload.name,
        slug=payload.slug,
        brief_markdown=payload.brief_markdown,
        settings_json=payload.settings_json,
    )
    return CompanyResponse.model_validate(item)


@router.get("/default", response_model=CompanyResponse)
async def get_default_company(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_authenticated_user),
):
    service = CompanyService(db)
    item = await service.get_or_create_default(current_user.id)
    return CompanyResponse.model_validate(item)


@router.patch("/{company_id}", response_model=CompanyResponse)
async def update_company(
    company_id: str,
    payload: CompanyUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_authenticated_user),
):
    service = CompanyService(db)
    item = await service.update(
        current_user.id,
        company_id,
        name=payload.name,
        brief_markdown=payload.brief_markdown,
        settings_json=payload.settings_json,
    )
    return CompanyResponse.model_validate(item)
