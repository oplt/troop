from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps.auth import get_current_user
from backend.db.session import get_db
from backend.modules.identity_access.models import User
from backend.modules.orchestration.presenters import (
    to_model_capability_response,
    to_provider_response,
)
from backend.modules.orchestration.schemas import (
    ModelCapabilityResponse,
    ProviderCompareRequest,
    ProviderCompareResponse,
    ProviderConfigCreate,
    ProviderConfigResponse,
    ProviderConfigUpdate,
    ProviderHealthSummaryResponse,
    ProviderModelListResponse,
)
from backend.modules.orchestration.services.provider_runtime_service import ProviderRuntimeService
from backend.modules.orchestration.services.service import OrchestrationService

router = APIRouter(prefix="/providers", tags=["orchestration-providers"])


@router.get("", response_model=list[ProviderConfigResponse])
async def list_providers(
    project_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return [
        to_provider_response(item)
        for item in await OrchestrationService(db).list_providers(current_user, project_id)
    ]


@router.post("", response_model=ProviderConfigResponse, status_code=201)
async def create_provider(
    payload: ProviderConfigCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return to_provider_response(
        await OrchestrationService(db).create_provider(current_user, payload.model_dump())
    )


@router.patch("/{provider_id}", response_model=ProviderConfigResponse)
async def update_provider(
    provider_id: str,
    payload: ProviderConfigUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return to_provider_response(
        await OrchestrationService(db).update_provider(
            current_user, provider_id, payload.model_dump(exclude_unset=True)
        )
    )


@router.delete("/{provider_id}", status_code=204)
async def delete_provider(
    provider_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await OrchestrationService(db).delete_provider(current_user, provider_id)
    return Response(status_code=204)


@router.post("/{provider_id}/test")
async def test_provider_connection(
    provider_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await OrchestrationService(db).test_provider(current_user, provider_id)


@router.post("/{provider_id}/runtime/start")
async def start_provider_runtime(
    provider_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await ProviderRuntimeService(db).start(current_user, provider_id)


@router.post("/health-check")
async def health_check_providers(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await OrchestrationService(db).run_provider_health_checks_for_user(current_user)


@router.get("/health-summary", response_model=list[ProviderHealthSummaryResponse])
async def provider_health_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await OrchestrationService(db).provider_health_summary(current_user)


@router.get("/{provider_id}/models", response_model=ProviderModelListResponse)
async def list_provider_models(
    provider_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await OrchestrationService(db).list_provider_models_for_user(current_user, provider_id)


@router.get("/model-capabilities", response_model=list[ModelCapabilityResponse])
async def list_model_capabilities(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return [
        to_model_capability_response(item)
        for item in await OrchestrationService(db).list_model_capabilities(current_user)
    ]


@router.post("/compare", response_model=ProviderCompareResponse)
async def compare_provider_outputs(
    payload: ProviderCompareRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await OrchestrationService(db).compare_providers(current_user, payload.model_dump())
