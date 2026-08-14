"""Platform configuration, metadata, and module gating."""

from __future__ import annotations

from fastapi import HTTPException

from backend.core.cache import (
    get_cached_platform_metadata,
    invalidate_platform_metadata_cache,
    set_cached_platform_metadata,
)
from backend.core.config import settings
from backend.modules.identity_access.models import User
from backend.modules.platform.catalog import (
    DEFAULT_EMAIL_TEMPLATES,
    DEFAULT_FEATURE_FLAGS,
    DEFAULT_PLANS,
    MODULE_CATALOG,
    MODULE_PACKS,
    SETTING_APP_NAME,
    SETTING_CORE_DOMAIN_PLURAL,
    SETTING_CORE_DOMAIN_SINGULAR,
    SETTING_MODULE_OVERRIDE_PREFIX,
    SETTING_MODULE_PACK,
    SETTING_MFA_ENABLED,
)
from backend.modules.platform.schemas import (
    ModuleCatalogItem,
    ModulePackResponse,
    PlatformConfigResponse,
    PlatformMetadataResponse,
)


class PlatformConfigMixin:
    async def ensure_defaults(self) -> None:
        changed = False

        for key, value, description in (
            (SETTING_APP_NAME, settings.APP_NAME, "Clone-specific app display name."),
            (
                SETTING_CORE_DOMAIN_SINGULAR,
                settings.CORE_DOMAIN_SINGULAR,
                "Singular label for the core domain surfaced in the UI.",
            ),
            (
                SETTING_CORE_DOMAIN_PLURAL,
                settings.CORE_DOMAIN_PLURAL,
                "Plural label for the core domain surfaced in the UI.",
            ),
            (
                SETTING_MODULE_PACK,
                settings.PLATFORM_DEFAULT_MODULE_PACK,
                "Active module pack for optional platform capabilities.",
            ),
            (
                SETTING_MFA_ENABLED,
                "false",
                "Whether MFA authentication is shown and enforced on login.",
            ),
        ):
            if await self.settings_repo.get_by_key(key) is None:
                await self.settings_repo.create(key=key, value=value, description=description)
                changed = True

        for plan_payload in DEFAULT_PLANS:
            if await self.repo.get_plan_by_code(plan_payload["code"]) is None:
                await self.repo.create_plan(**plan_payload)
                changed = True

        for flag_payload in DEFAULT_FEATURE_FLAGS:
            if await self.repo.get_feature_flag_by_key(flag_payload["key"]) is None:
                await self.repo.create_feature_flag(**flag_payload)
                changed = True

        for template_payload in DEFAULT_EMAIL_TEMPLATES:
            if await self.repo.get_email_template_by_key(template_payload["key"]) is None:
                await self.repo.create_email_template(**template_payload)
                changed = True

        if changed:
            await self.db.commit()

    async def get_platform_metadata(self) -> PlatformMetadataResponse:
        cached = await get_cached_platform_metadata()
        if cached is not None:
            return PlatformMetadataResponse(**cached)
        config = await self.get_platform_config()
        response = PlatformMetadataResponse(
            app_name=config.app_name,
            core_domain_singular=config.core_domain_singular,
            core_domain_plural=config.core_domain_plural,
            module_pack=config.module_pack,
            enabled_modules=config.enabled_modules,
            module_catalog=config.module_catalog,
            available_module_packs=config.available_module_packs,
            mfa_enabled=config.mfa_enabled,
        )
        await set_cached_platform_metadata(response.model_dump(mode="json"))
        return response

    async def get_platform_config(self) -> PlatformConfigResponse:
        platform_settings = await self.settings_repo.list_by_prefix("platform.")
        setting_map = {item.key: item.value for item in platform_settings}

        module_pack = setting_map.get(SETTING_MODULE_PACK, settings.PLATFORM_DEFAULT_MODULE_PACK)
        if module_pack not in MODULE_PACKS:
            module_pack = settings.PLATFORM_DEFAULT_MODULE_PACK

        explicit_overrides: dict[str, bool] = {}
        for item in MODULE_CATALOG:
            raw_value = setting_map.get(f"{SETTING_MODULE_OVERRIDE_PREFIX}{item['key']}")
            if raw_value is not None:
                explicit_overrides[item["key"]] = self._parse_bool(raw_value)

        enabled_modules = self._resolve_enabled_modules(module_pack, explicit_overrides)
        module_catalog = [
            ModuleCatalogItem(
                key=item["key"],
                label=item["label"],
                description=item["description"],
                user_visible=item["user_visible"],
                enabled=item["key"] in enabled_modules,
            )
            for item in MODULE_CATALOG
        ]

        mfa_enabled = self._parse_bool(setting_map.get(SETTING_MFA_ENABLED, "false"))

        return PlatformConfigResponse(
            app_name=setting_map.get(SETTING_APP_NAME, settings.APP_NAME),
            core_domain_singular=setting_map.get(
                SETTING_CORE_DOMAIN_SINGULAR, settings.CORE_DOMAIN_SINGULAR
            ),
            core_domain_plural=setting_map.get(
                SETTING_CORE_DOMAIN_PLURAL, settings.CORE_DOMAIN_PLURAL
            ),
            module_pack=module_pack,
            enabled_modules=enabled_modules,
            module_catalog=module_catalog,
            available_module_packs=[
                ModulePackResponse(key=key, **pack_payload)
                for key, pack_payload in MODULE_PACKS.items()
            ],
            module_overrides=explicit_overrides,
            mfa_enabled=mfa_enabled,
        )

    async def update_platform_config(
        self,
        *,
        app_name: str | None,
        core_domain_singular: str | None,
        core_domain_plural: str | None,
        module_pack: str | None,
        module_overrides: dict[str, bool] | None,
        mfa_enabled: bool | None,
    ) -> PlatformConfigResponse:
        current_config = await self.get_platform_config()
        next_pack = module_pack or current_config.module_pack
        if next_pack not in MODULE_PACKS:
            raise HTTPException(status_code=422, detail="Unknown module pack")

        if app_name is not None:
            await self._upsert_setting(
                SETTING_APP_NAME, app_name, "Clone-specific app display name."
            )
        if core_domain_singular is not None:
            await self._upsert_setting(
                SETTING_CORE_DOMAIN_SINGULAR,
                core_domain_singular,
                "Singular label for the core domain surfaced in the UI.",
            )
        if core_domain_plural is not None:
            await self._upsert_setting(
                SETTING_CORE_DOMAIN_PLURAL,
                core_domain_plural,
                "Plural label for the core domain surfaced in the UI.",
            )
        if module_pack is not None:
            await self._upsert_setting(
                SETTING_MODULE_PACK,
                module_pack,
                "Active module pack for optional platform capabilities.",
            )

        if mfa_enabled is not None:
            await self._upsert_setting(
                SETTING_MFA_ENABLED,
                self._serialize_bool(mfa_enabled),
                "Whether MFA authentication is shown and enforced on login.",
            )

        if module_overrides is not None:
            pack_modules = set(MODULE_PACKS[next_pack]["modules"])
            valid_module_keys = {item["key"] for item in MODULE_CATALOG}
            for key, enabled in module_overrides.items():
                if key not in valid_module_keys:
                    raise HTTPException(status_code=422, detail=f"Unknown module key: {key}")
                setting_key = f"{SETTING_MODULE_OVERRIDE_PREFIX}{key}"
                should_exist = enabled != (key in pack_modules)
                existing = await self.settings_repo.get_by_key(setting_key)
                if should_exist:
                    if existing is None:
                        await self.settings_repo.create(
                            key=setting_key,
                            value=self._serialize_bool(enabled),
                            description=f"Explicit module override for {key}.",
                        )
                    else:
                        existing.value = self._serialize_bool(enabled)
                elif existing is not None:
                    await self.settings_repo.delete(existing)

        await self.db.commit()
        await invalidate_platform_metadata_cache()
        return await self.get_platform_config()
    async def ensure_module_enabled(self, module_key: str) -> None:
        metadata = await self.get_platform_metadata()
        if module_key not in metadata.enabled_modules:
            raise HTTPException(status_code=404, detail=f"Module `{module_key}` is not enabled")

    async def _normalize_default_plan(self, active_plan: SubscriptionPlan) -> None:
        if not active_plan.is_default:
            return
        plans = await self.repo.list_plans()
        for plan in plans:
            if plan.id != active_plan.id and plan.is_default:
                plan.is_default = False

    async def _upsert_setting(self, key: str, value: str, description: str) -> None:
        setting = await self.settings_repo.get_by_key(key)
        if setting is None:
            await self.settings_repo.create(key=key, value=value, description=description)
        else:
            setting.value = value
            setting.description = description

    @staticmethod
    def _resolve_enabled_modules(
        module_pack: str, explicit_overrides: dict[str, bool]
    ) -> list[str]:
        enabled = set(MODULE_PACKS[module_pack]["modules"])
        for key, value in explicit_overrides.items():
            if value:
                enabled.add(key)
            else:
                enabled.discard(key)
        ordered_module_keys = [item["key"] for item in MODULE_CATALOG]
        return [key for key in ordered_module_keys if key in enabled]

    @staticmethod
    def _parse_bool(raw_value: str) -> bool:
        return raw_value.strip().lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def _serialize_bool(value: bool) -> str:
        return "true" if value else "false"
