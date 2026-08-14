"""In-memory connector manifest and provider registry."""

from __future__ import annotations

from backend.modules.workforce.connectors.manifest import ConnectorManifest
from backend.modules.workforce.connectors.provider import ConnectorProvider


class ConnectorManifestRegistry:
    _manifests: dict[str, ConnectorManifest] = {}
    _providers: dict[str, ConnectorProvider] = {}

    @classmethod
    def reset(cls) -> None:
        cls._manifests.clear()
        cls._providers.clear()

    @classmethod
    def register_manifest(cls, manifest: ConnectorManifest) -> None:
        cls._manifests[manifest.provider_slug] = manifest

    @classmethod
    def register_provider(cls, provider: ConnectorProvider) -> None:
        manifest = provider.manifest
        cls._providers[manifest.provider_slug] = provider
        cls._manifests.setdefault(manifest.provider_slug, manifest)

    @classmethod
    def get_manifest(cls, provider_slug: str) -> ConnectorManifest | None:
        return cls._manifests.get(provider_slug)

    @classmethod
    def get_provider(cls, provider_slug: str) -> ConnectorProvider | None:
        return cls._providers.get(provider_slug)

    @classmethod
    def list_manifests(cls) -> list[ConnectorManifest]:
        return sorted(cls._manifests.values(), key=lambda item: item.name.lower())

    @classmethod
    def list_providers(cls) -> list[ConnectorProvider]:
        return list(cls._providers.values())
