#!/usr/bin/env python3
"""Re-encrypt connector/provider secrets with the current SECRETS_ENCRYPTION_KEY.

Usage:
  1. Set SECRETS_ENCRYPTION_PREVIOUS_KEY to the old dedicated key (if rotating).
  2. Set SECRETS_ENCRYPTION_KEY to the new dedicated key.
  3. Run: python backend/tools/rotate_secrets_encryption.py
  4. Verify services boot and connector credentials still work.
  5. Remove SECRETS_ENCRYPTION_PREVIOUS_KEY after all rows re-encrypt.
"""

from __future__ import annotations

import argparse
import asyncio

from backend.db.session import SessionLocal
from backend.modules.github.models import GithubConnection
from backend.modules.orchestration.models import ProviderConfig
from backend.modules.orchestration.security import clear_secrets_fernet_cache, reencrypt_secret
from backend.modules.platform.models import WebhookEndpoint
from backend.modules.workforce.models import ConnectorInstallation, ConnectorOAuthState
from sqlalchemy import select


async def _rotate_column(model, column: str) -> tuple[int, int]:
    rotated = 0
    skipped = 0
    async with SessionLocal() as db:
        result = await db.execute(select(model))
        for row in result.scalars().all():
            current = getattr(row, column, None)
            if not current:
                continue
            refreshed = reencrypt_secret(current)
            if refreshed is None:
                skipped += 1
                continue
            if refreshed != current:
                setattr(row, column, refreshed)
                rotated += 1
        await db.commit()
    return rotated, skipped


async def rotate_all() -> dict[str, dict[str, int]]:
    clear_secrets_fernet_cache()
    targets = [
        ("provider_configs.encrypted_api_key", ProviderConfig, "encrypted_api_key"),
        ("connector_installations.secrets_ref", ConnectorInstallation, "secrets_ref"),
        ("github_connections.encrypted_token", GithubConnection, "encrypted_token"),
        ("webhook_endpoints.secret", WebhookEndpoint, "secret"),
        (
            "connector_oauth_states.encrypted_code_verifier",
            ConnectorOAuthState,
            "encrypted_code_verifier",
        ),
    ]
    summary: dict[str, dict[str, int]] = {}
    for label, model, column in targets:
        rotated, skipped = await _rotate_column(model, column)
        summary[label] = {"rotated": rotated, "undecryptable": skipped}
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    summary = asyncio.run(rotate_all())
    for label, counts in summary.items():
        print(
            f"{label}: rotated={counts['rotated']} undecryptable={counts['undecryptable']}"
        )


if __name__ == "__main__":
    main()
