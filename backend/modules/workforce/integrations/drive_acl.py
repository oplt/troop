"""Normalize and evaluate external drive ACL snapshots for RAG retrieval."""

from __future__ import annotations

from typing import Any


def normalize_google_drive_acl(*, file_body: dict[str, Any], owner_email: str | None = None) -> dict[str, Any]:
    permissions = []
    for item in file_body.get("permissions") or []:
        email = str((item.get("emailAddress") or "")).strip().lower()
        if email:
            permissions.append(email)
        elif str(item.get("type") or "") == "anyone":
            return {
                "owner_email": (owner_email or "").lower(),
                "allowed_emails": sorted(set(permissions)),
                "public": True,
            }
    owner = str((file_body.get("owners") or [{}])[0].get("emailAddress") or owner_email or "").lower()
    allowed = sorted({owner, *permissions} - {""})
    return {"owner_email": owner, "allowed_emails": allowed, "public": False}


def normalize_microsoft_drive_acl(*, file_body: dict[str, Any], owner_email: str | None = None) -> dict[str, Any]:
    allowed: set[str] = set()
    owner = owner_email or ""
    created_by = dict(file_body.get("createdBy") or {}).get("user") or {}
    owner = str(created_by.get("email") or created_by.get("userPrincipalName") or owner).lower()
    if owner:
        allowed.add(owner)
    for item in file_body.get("permissions") or []:
        granted = dict(item.get("grantedToV2") or item.get("grantedTo") or {})
        user = dict(granted.get("user") or {})
        email = str(user.get("email") or user.get("userPrincipalName") or "").lower()
        if email:
            allowed.add(email)
        link = dict(item.get("link") or {})
        if link.get("scope") in {"anonymous", "organization"}:
            return {
                "owner_email": owner,
                "allowed_emails": sorted(allowed),
                "public": link.get("scope") == "anonymous",
            }
    return {"owner_email": owner, "allowed_emails": sorted(allowed), "public": False}


def actor_can_read_acl(acl_snapshot: dict[str, Any] | None, *, actor_email: str | None) -> bool:
    if not acl_snapshot:
        return False
    if acl_snapshot.get("public"):
        return True
    email = str(actor_email or "").strip().lower()
    if not email:
        return False
    allowed = {str(item).lower() for item in acl_snapshot.get("allowed_emails") or []}
    owner = str(acl_snapshot.get("owner_email") or "").lower()
    return email == owner or email in allowed
