from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.platform.api_keys_service import PlatformApiKeysMixin
from backend.modules.platform.billing_service import PlatformBillingMixin
from backend.modules.platform.catalog import (
    DEFAULT_EMAIL_TEMPLATES,
    DEFAULT_FEATURE_FLAGS,
    DEFAULT_PLANS,
    MODULE_CATALOG,
    MODULE_PACKS,
)
from backend.modules.platform.config_service import PlatformConfigMixin
from backend.modules.platform.email_templates_service import PlatformEmailTemplatesMixin
from backend.modules.platform.feature_flags_service import PlatformFeatureFlagsMixin
from backend.modules.platform.repository import PlatformRepository
from backend.modules.platform.webhooks_service import PlatformWebhooksMixin
from backend.modules.settings.repository import SettingsRepository

# Backward-compatible re-exports for callers importing catalog constants from service.
__all__ = [
    "PlatformService",
    "MODULE_CATALOG",
    "MODULE_PACKS",
    "DEFAULT_PLANS",
    "DEFAULT_FEATURE_FLAGS",
    "DEFAULT_EMAIL_TEMPLATES",
]


class PlatformService(
    PlatformConfigMixin,
    PlatformBillingMixin,
    PlatformApiKeysMixin,
    PlatformWebhooksMixin,
    PlatformFeatureFlagsMixin,
    PlatformEmailTemplatesMixin,
):
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = PlatformRepository(db)
        self.settings_repo = SettingsRepository(db)
