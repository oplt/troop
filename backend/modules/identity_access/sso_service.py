"""OIDC SSO login for enterprise identity providers (ENT-001)."""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.cache import redis_client
from backend.core.config import settings
from backend.core.http_clients import managed_http_client
from backend.core.security import generate_refresh_token, hash_refresh_token
from backend.modules.audit.repository import AuditRepository
from backend.modules.identity_access.models import ExternalIdentity, IdentityProvider, User
from backend.modules.identity_access.repository import IdentityRepository
from backend.modules.identity_access.workspace_repository import WorkspaceRepository
from backend.modules.orchestration.security import decrypt_secret, encrypt_secret

_SSO_STATE_TTL_SECONDS = 600
_DEFAULT_SCOPES = ("openid", "email", "profile")


def _hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def _email_domain(email: str) -> str:
    parts = email.lower().split("@", 1)
    return parts[1] if len(parts) == 2 else ""


class SsoService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = IdentityRepository(db)

    async def list_public_providers(self) -> list[dict[str, str]]:
        result = await self.db.execute(
            select(IdentityProvider)
            .where(IdentityProvider.enabled.is_(True))
            .order_by(IdentityProvider.name.asc())
        )
        return [
            {"slug": row.slug, "name": row.name, "provider_type": row.provider_type}
            for row in result.scalars().all()
        ]

    async def _get_provider(self, slug: str) -> IdentityProvider:
        result = await self.db.execute(
            select(IdentityProvider).where(IdentityProvider.slug == slug)
        )
        provider = result.scalar_one_or_none()
        if provider is None or not provider.enabled:
            raise HTTPException(status_code=404, detail="identity provider not found")
        return provider

    def _client_secret(self, provider: IdentityProvider) -> str:
        if not provider.secrets_ref:
            raise HTTPException(status_code=422, detail="identity provider missing client secret")
        raw = decrypt_secret(provider.secrets_ref)
        if not raw:
            raise HTTPException(status_code=422, detail="identity provider client secret unavailable")
        return raw

    async def _discover(self, issuer: str) -> dict[str, Any]:
        base = issuer.rstrip("/")
        url = f"{base}/.well-known/openid-configuration"
        async with managed_http_client("sso_oidc") as client:
            response = await client.get(url)
        if response.status_code >= 400:
            raise HTTPException(status_code=422, detail="OIDC discovery failed")
        return response.json()

    async def build_authorize_url(self, slug: str, *, redirect_after: str | None = None) -> str:
        provider = await self._get_provider(slug)
        discovery = await self._discover(provider.issuer)
        authorize_endpoint = str(discovery.get("authorization_endpoint") or "")
        if not authorize_endpoint:
            raise HTTPException(status_code=422, detail="OIDC authorization endpoint missing")

        state = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(48)
        payload = {
            "provider_id": provider.id,
            "provider_slug": provider.slug,
            "code_verifier": verifier,
            "redirect_after": redirect_after or settings.FRONTEND_URL,
        }
        await redis_client.setex(
            f"sso:state:{_hash_secret(state)}",
            _SSO_STATE_TTL_SECONDS,
            json.dumps(payload),
        )

        scopes = list(provider.scopes_json or list(_DEFAULT_SCOPES))
        params = {
            "client_id": provider.client_id,
            "response_type": "code",
            "scope": " ".join(scopes),
            "redirect_uri": self.callback_url(),
            "state": state,
            "code_challenge": _pkce_challenge(verifier),
            "code_challenge_method": "S256",
        }
        return f"{authorize_endpoint}?{urlencode(params)}"

    @staticmethod
    def callback_url() -> str:
        base = settings.PUBLIC_API_BASE.rstrip("/")
        return f"{base}/auth/sso/callback"

    async def handle_callback(
        self,
        *,
        code: str,
        state: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> dict[str, Any]:
        state_key = f"sso:state:{_hash_secret(state)}"
        raw_state = await redis_client.get(state_key)
        if not raw_state:
            raise HTTPException(status_code=400, detail="invalid or expired SSO state")
        await redis_client.delete(state_key)
        state_payload = json.loads(raw_state)

        result = await self.db.execute(
            select(IdentityProvider).where(IdentityProvider.id == state_payload["provider_id"])
        )
        provider = result.scalar_one_or_none()
        if provider is None or not provider.enabled:
            raise HTTPException(status_code=400, detail="identity provider unavailable")

        discovery = await self._discover(provider.issuer)
        token_endpoint = str(discovery.get("token_endpoint") or "")
        if not token_endpoint:
            raise HTTPException(status_code=422, detail="OIDC token endpoint missing")

        token_data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.callback_url(),
            "client_id": provider.client_id,
            "client_secret": self._client_secret(provider),
            "code_verifier": state_payload["code_verifier"],
        }
        async with managed_http_client("sso_oidc") as client:
            token_response = await client.post(
                token_endpoint,
                data=token_data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        if token_response.status_code >= 400:
            raise HTTPException(status_code=401, detail="OIDC token exchange failed")
        token_json = token_response.json()
        id_token = str(token_json.get("id_token") or "")
        access_token = str(token_json.get("access_token") or "")

        profile = await self._fetch_user_profile(discovery, access_token, id_token)
        subject = str(profile.get("sub") or "")
        email = str(profile.get("email") or "").strip().lower()
        name = str(profile.get("name") or profile.get("given_name") or "").strip() or None
        if not subject or not email:
            raise HTTPException(status_code=401, detail="OIDC profile missing required claims")

        allowlist = [str(item).lower() for item in (provider.domain_allowlist_json or [])]
        if allowlist and _email_domain(email) not in allowlist:
            raise HTTPException(status_code=403, detail="email domain not allowed for this identity provider")

        user = await self._resolve_user(provider, subject, email, name)
        external = await self._touch_external_identity(provider, subject, user, email, profile)

        raw_refresh = generate_refresh_token()
        expires_at = datetime.now(UTC) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        session = await self.repo.create_refresh_session(
            user_id=user.id,
            token_hash=hash_refresh_token(raw_refresh),
            expires_at=expires_at,
        )
        await AuditRepository(self.db).log(
            "auth.sso_login",
            user_id=user.id,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata={
                "provider_slug": provider.slug,
                "subject": subject,
                "external_identity_id": external.id,
                "provisioned": profile.get("_provisioned", False),
            },
        )
        await self.db.commit()

        return {
            "refresh_token": raw_refresh,
            "session_id": session.id,
            "user": user,
            "redirect_after": state_payload.get("redirect_after") or settings.FRONTEND_URL,
        }

    async def _fetch_user_profile(
        self,
        discovery: dict[str, Any],
        access_token: str,
        id_token: str,
    ) -> dict[str, Any]:
        userinfo = str(discovery.get("userinfo_endpoint") or "")
        if userinfo and access_token:
            async with managed_http_client("sso_oidc") as client:
                response = await client.get(
                    userinfo,
                    headers={"Authorization": f"Bearer {access_token}"},
                )
            if response.status_code < 400:
                data = response.json()
                if isinstance(data, dict) and data.get("sub"):
                    return data
        if id_token:
            parts = id_token.split(".")
            if len(parts) >= 2:
                padded = parts[1] + "=" * (-len(parts[1]) % 4)
                try:
                    payload = json.loads(base64.urlsafe_b64decode(padded.encode()))
                    if isinstance(payload, dict):
                        return payload
                except (json.JSONDecodeError, ValueError):
                    pass
        raise HTTPException(status_code=401, detail="unable to resolve OIDC user profile")

    async def _resolve_user(
        self,
        provider: IdentityProvider,
        subject: str,
        email: str,
        full_name: str | None,
    ) -> User:
        result = await self.db.execute(
            select(ExternalIdentity).where(
                ExternalIdentity.provider_id == provider.id,
                ExternalIdentity.subject == subject,
            )
        )
        linked = result.scalar_one_or_none()
        if linked is not None:
            user = await self.repo.get_user_by_id(linked.user_id)
            if user is None or not user.is_active:
                raise HTTPException(status_code=403, detail="linked user unavailable")
            return user

        existing = await self.repo.get_user_by_email(email)
        if existing is not None:
            if not existing.is_active:
                raise HTTPException(status_code=403, detail="account disabled")
            return existing

        user = User(
            email=email,
            password_hash=None,
            full_name=full_name,
            auth_provider="oidc",
            external_auth_only=True,
            is_verified=True,
            is_active=True,
        )
        self.db.add(user)
        await self.db.flush()
        await WorkspaceRepository(self.db).ensure_default_workspace(
            user_id=user.id,
            email=user.email,
            full_name=user.full_name,
        )
        return user

    async def _touch_external_identity(
        self,
        provider: IdentityProvider,
        subject: str,
        user: User,
        email: str,
        profile: dict[str, Any],
    ) -> ExternalIdentity:
        result = await self.db.execute(
            select(ExternalIdentity).where(
                ExternalIdentity.provider_id == provider.id,
                ExternalIdentity.subject == subject,
            )
        )
        row = result.scalar_one_or_none()
        now = datetime.now(UTC)
        if row is None:
            row = ExternalIdentity(
                provider_id=provider.id,
                subject=subject,
                user_id=user.id,
                email=email,
                last_login_at=now,
                metadata_json={"claims": {k: profile.get(k) for k in ("email", "name", "sub")}},
            )
            self.db.add(row)
            profile["_provisioned"] = True
            await AuditRepository(self.db).log(
                "auth.sso_provision",
                user_id=user.id,
                resource_type="user",
                resource_id=user.id,
                metadata={"provider_slug": provider.slug, "subject": subject, "email": email},
            )
        else:
            row.user_id = user.id
            row.email = email
            row.last_login_at = now
        await self.db.flush()
        return row

    async def test_provider(self, provider: IdentityProvider) -> dict[str, Any]:
        discovery = await self._discover(provider.issuer)
        return {
            "issuer": provider.issuer,
            "authorization_endpoint": discovery.get("authorization_endpoint"),
            "token_endpoint": discovery.get("token_endpoint"),
            "userinfo_endpoint": discovery.get("userinfo_endpoint"),
        }

    @staticmethod
    def encrypt_client_secret(secret: str) -> str | None:
        cleaned = secret.strip()
        if not cleaned:
            return None
        return encrypt_secret(cleaned)
