"""Tests for Google Drive + Microsoft Drive connector integrations (CONN-006)."""

from __future__ import annotations

from backend.modules.rag.retrieval import RetrieverService
from backend.modules.rag.schemas import RagChunkMatch, RagSearchFilters
from backend.modules.workforce.integrations.drive_acl import (
    actor_can_read_acl,
    normalize_google_drive_acl,
    normalize_microsoft_drive_acl,
)


def test_google_drive_acl_normalization_marks_public() -> None:
    snapshot = normalize_google_drive_acl(
        file_body={
            "owners": [{"emailAddress": "owner@example.com"}],
            "permissions": [{"type": "anyone", "role": "reader"}],
        }
    )
    assert snapshot["public"] is True
    assert actor_can_read_acl(snapshot, actor_email="stranger@example.com")


def test_google_drive_acl_denies_revoked_reader() -> None:
    snapshot = normalize_google_drive_acl(
        file_body={
            "owners": [{"emailAddress": "owner@example.com"}],
            "permissions": [{"type": "user", "emailAddress": "reader@example.com", "role": "reader"}],
        }
    )
    assert actor_can_read_acl(snapshot, actor_email="reader@example.com")
    assert not actor_can_read_acl(snapshot, actor_email="revoked@example.com")


def test_microsoft_drive_acl_allows_owner_and_granted_user() -> None:
    snapshot = normalize_microsoft_drive_acl(
        file_body={
            "createdBy": {"user": {"email": "owner@example.com"}},
            "permissions": [
                {
                    "grantedToV2": {"user": {"email": "reader@example.com"}},
                }
            ],
        }
    )
    assert actor_can_read_acl(snapshot, actor_email="owner@example.com")
    assert actor_can_read_acl(snapshot, actor_email="reader@example.com")
    assert not actor_can_read_acl(snapshot, actor_email="blocked@example.com")


def test_drive_tools_registered_in_catalog() -> None:
    from backend.modules.workforce.constants import NATIVE_TOOL_CATALOG

    google = {item["slug"] for item in NATIVE_TOOL_CATALOG if item["slug"].startswith("google_drive.")}
    microsoft = {
        item["slug"] for item in NATIVE_TOOL_CATALOG if item["slug"].startswith("microsoft_drive.")
    }
    assert google >= {
        "google_drive.search_files",
        "google_drive.get_file_metadata",
        "google_drive.get_file_content",
    }
    assert microsoft >= {
        "microsoft_drive.search_files",
        "microsoft_drive.get_file_metadata",
        "microsoft_drive.get_file_content",
    }


def test_drive_tools_are_read_only_in_catalog() -> None:
    from backend.modules.workforce.constants import NATIVE_TOOL_CATALOG

    by_slug = {item["slug"]: item for item in NATIVE_TOOL_CATALOG}
    for slug in (
        "google_drive.search_files",
        "google_drive.get_file_metadata",
        "google_drive.get_file_content",
        "microsoft_drive.search_files",
        "microsoft_drive.get_file_metadata",
        "microsoft_drive.get_file_content",
    ):
        assert by_slug[slug]["requires_approval"] is False
        assert by_slug[slug]["risk_level"] == "low"


def test_drive_manifests_registered() -> None:
    from backend.modules.workforce.connectors import (
        ConnectorManifestRegistry,
        register_builtin_manifests,
    )

    ConnectorManifestRegistry.reset()
    register_builtin_manifests()
    for slug in ("google_drive", "microsoft_drive"):
        manifest = ConnectorManifestRegistry.get_manifest(slug)
        assert manifest is not None
        action_slugs = {item.slug for item in manifest.actions}
        assert f"{slug}.search_files" in action_slugs
        assert f"{slug}.get_file_content" in action_slugs


def test_retriever_filters_revoked_drive_acl_matches() -> None:
    allowed = RagChunkMatch(
        chunk_id="c1",
        document_id="d1",
        title="allowed.txt",
        content="secret",
        chunk_index=0,
        score=0.9,
        metadata={
            "source_kind": "google_drive",
            "acl_snapshot": {
                "public": False,
                "owner_email": "owner@example.com",
                "allowed_emails": ["reader@example.com"],
            },
        },
    )
    denied = RagChunkMatch(
        chunk_id="c2",
        document_id="d2",
        title="denied.txt",
        content="secret",
        chunk_index=0,
        score=0.95,
        metadata={
            "source_kind": "microsoft_drive",
            "acl_snapshot": {
                "public": False,
                "owner_email": "owner@example.com",
                "allowed_emails": ["other@example.com"],
            },
        },
    )
    local = RagChunkMatch(
        chunk_id="c3",
        document_id="d3",
        title="local.txt",
        content="local",
        chunk_index=0,
        score=0.5,
        metadata={"source_kind": "upload"},
    )
    filtered = RetrieverService._filter_drive_acl_matches(  # noqa: SLF001
        [allowed, denied, local],
        actor_email="reader@example.com",
    )
    assert {item.chunk_id for item in filtered} == {"c1", "c3"}


def test_retriever_excludes_all_drive_docs_without_actor_email() -> None:
    drive = RagChunkMatch(
        chunk_id="c1",
        document_id="d1",
        title="drive.txt",
        content="secret",
        chunk_index=0,
        score=0.9,
        metadata={
            "source_kind": "google_drive",
            "acl_snapshot": {"public": True, "allowed_emails": []},
        },
    )
    filtered = RetrieverService._filter_drive_acl_matches([drive], actor_email=None)  # noqa: SLF001
    assert filtered == []


def test_rag_search_filters_include_actor_email() -> None:
    filters = RagSearchFilters(project_id="p1", actor_email="reader@example.com")
    assert filters.actor_email == "reader@example.com"
