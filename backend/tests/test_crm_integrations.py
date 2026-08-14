"""Tests for HubSpot + Salesforce CRM connector integrations (CONN-008)."""

from __future__ import annotations

from backend.modules.orchestration.execution.hitl.exact_effect import (
    compute_effect_hash,
    normalize_proposed_effect,
)
from backend.modules.workforce.integrations.crm_records import (
    HUBSPOT_CONTACT_UPDATE_ALLOWLIST,
    SALESFORCE_CONTACT_UPDATE_ALLOWLIST,
    canonical_hubspot_crm_arguments,
    canonical_salesforce_crm_arguments,
    filter_allowlisted_fields,
    hubspot_crm_arguments_hash,
    salesforce_crm_arguments_hash,
)


def test_allowlisted_fields_filter_rejects_unknown_keys() -> None:
    fields = filter_allowlisted_fields(
        {
            "firstname": "Ada",
            "secret_token": "nope",
            "Email": "ada@example.com",
        },
        allowlist=HUBSPOT_CONTACT_UPDATE_ALLOWLIST,
    )
    assert fields == {"firstname": "Ada"}
    sf_fields = filter_allowlisted_fields(
        {"FirstName": "Ada", "SSN__c": "secret"},
        allowlist=SALESFORCE_CONTACT_UPDATE_ALLOWLIST,
    )
    assert sf_fields == {"FirstName": "Ada"}


def test_hubspot_crm_hash_is_canonical() -> None:
    base = {
        "provider": "hubspot",
        "connector_installation_id": "install-a",
        "contact_id": "123",
        "fields": {"firstname": "Ada", "email": "ada@example.com"},
    }
    reordered = {**base, "fields": {"email": "ada@example.com", "firstname": "Ada"}}
    assert hubspot_crm_arguments_hash(base) == hubspot_crm_arguments_hash(reordered)
    assert canonical_hubspot_crm_arguments(base)["record_id"] == "123"


def test_salesforce_crm_hash_is_canonical() -> None:
    base = {
        "provider": "salesforce",
        "connector_installation_id": "install-b",
        "contact_id": "003ABC",
        "email_subject": "Hello",
        "email_body": "Checking in",
    }
    assert salesforce_crm_arguments_hash(base) == salesforce_crm_arguments_hash(dict(base))
    assert canonical_salesforce_crm_arguments(base)["email_subject"] == "Hello"


def test_exact_effect_normalizes_hubspot_mutations() -> None:
    arguments = {
        "connector_installation_id": "install-a",
        "contact_id": "123",
        "fields": {"firstname": "Ada"},
    }
    normalized = normalize_proposed_effect("hubspot.update_contact", arguments)
    assert normalized["record_id"] == "123"
    assert compute_effect_hash(normalized, action_key="hubspot.update_contact") == hubspot_crm_arguments_hash(
        arguments
    )


def test_crm_tools_registered_in_catalog() -> None:
    from backend.modules.workforce.constants import NATIVE_TOOL_CATALOG

    hubspot = {item["slug"] for item in NATIVE_TOOL_CATALOG if item["slug"].startswith("hubspot.")}
    salesforce = {
        item["slug"] for item in NATIVE_TOOL_CATALOG if item["slug"].startswith("salesforce.")
    }
    assert hubspot >= {
        "hubspot.search_contacts",
        "hubspot.get_contact",
        "hubspot.search_companies",
        "hubspot.get_company",
        "hubspot.update_contact",
        "hubspot.create_note",
        "hubspot.send_email",
    }
    assert salesforce >= {
        "salesforce.search_contacts",
        "salesforce.get_contact",
        "salesforce.search_accounts",
        "salesforce.get_account",
        "salesforce.update_contact",
        "salesforce.create_task",
        "salesforce.send_email",
    }


def test_crm_mutations_require_approval_in_catalog() -> None:
    from backend.modules.workforce.constants import NATIVE_TOOL_CATALOG

    by_slug = {item["slug"]: item for item in NATIVE_TOOL_CATALOG}
    for slug in (
        "hubspot.update_contact",
        "hubspot.create_note",
        "hubspot.send_email",
        "salesforce.update_contact",
        "salesforce.create_task",
        "salesforce.send_email",
    ):
        assert by_slug[slug]["requires_approval"] is True
    for slug in ("hubspot.search_contacts", "salesforce.get_contact"):
        assert by_slug[slug]["requires_approval"] is False


def test_crm_manifests_registered() -> None:
    from backend.modules.workforce.connectors import (
        ConnectorManifestRegistry,
        register_builtin_manifests,
    )

    ConnectorManifestRegistry.reset()
    register_builtin_manifests()
    for slug in ("hubspot", "salesforce"):
        manifest = ConnectorManifestRegistry.get_manifest(slug)
        assert manifest is not None
        action_slugs = {item.slug for item in manifest.actions}
        assert f"{slug}.search_contacts" in action_slugs
        assert f"{slug}.send_email" in action_slugs
