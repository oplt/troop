"""CRM record normalization, field allowlists, and approval fingerprints."""

from __future__ import annotations

from typing import Any

from backend.modules.orchestration.tool_execution_context import arguments_hash

HUBSPOT_CONTACT_UPDATE_ALLOWLIST = frozenset(
    {
        "firstname",
        "lastname",
        "email",
        "phone",
        "jobtitle",
        "company",
        "website",
        "lifecyclestage",
        "hs_lead_status",
    }
)

SALESFORCE_CONTACT_UPDATE_ALLOWLIST = frozenset(
    {
        "FirstName",
        "LastName",
        "Email",
        "Phone",
        "Title",
        "Department",
        "MailingCity",
        "MailingState",
        "MailingCountry",
        "LeadSource",
    }
)


def filter_allowlisted_fields(
    fields: dict[str, Any] | None, *, allowlist: frozenset[str]
) -> dict[str, str]:
    allowed: dict[str, str] = {}
    for key, value in dict(fields or {}).items():
        if key in allowlist and value is not None and str(value).strip():
            allowed[key] = str(value)
    return allowed


def _sorted_fields(fields: dict[str, Any] | None) -> dict[str, str]:
    filtered = {str(k): str(v) for k, v in dict(fields or {}).items() if v is not None}
    return dict(sorted(filtered.items()))


def canonical_hubspot_crm_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    return {
        "provider": "hubspot",
        "connector_installation_id": str(arguments.get("connector_installation_id") or ""),
        "record_id": str(
            arguments.get("record_id")
            or arguments.get("contact_id")
            or arguments.get("company_id")
            or ""
        ),
        "record_type": str(arguments.get("record_type") or "contact"),
        "query": str(arguments.get("query") or ""),
        "fields": _sorted_fields(arguments.get("fields")),
        "note_body": str(arguments.get("note_body") or arguments.get("body") or ""),
        "email_to": str(arguments.get("email_to") or arguments.get("to") or ""),
        "email_subject": str(arguments.get("email_subject") or arguments.get("subject") or ""),
        "email_body": str(arguments.get("email_body") or arguments.get("message") or ""),
        "email_id": str(arguments.get("email_id") or ""),
    }


def canonical_salesforce_crm_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    return {
        "provider": "salesforce",
        "connector_installation_id": str(arguments.get("connector_installation_id") or ""),
        "record_id": str(
            arguments.get("record_id")
            or arguments.get("contact_id")
            or arguments.get("account_id")
            or ""
        ),
        "record_type": str(arguments.get("record_type") or "contact"),
        "query": str(arguments.get("query") or arguments.get("soql") or ""),
        "fields": _sorted_fields(arguments.get("fields")),
        "task_subject": str(arguments.get("task_subject") or arguments.get("subject") or ""),
        "task_description": str(
            arguments.get("task_description") or arguments.get("description") or ""
        ),
        "email_to": str(arguments.get("email_to") or arguments.get("to") or ""),
        "email_subject": str(arguments.get("email_subject") or arguments.get("subject") or ""),
        "email_body": str(arguments.get("email_body") or arguments.get("message") or ""),
    }


def hubspot_crm_arguments_hash(arguments: dict[str, Any]) -> str:
    return arguments_hash(canonical_hubspot_crm_arguments(arguments))


def salesforce_crm_arguments_hash(arguments: dict[str, Any]) -> str:
    return arguments_hash(canonical_salesforce_crm_arguments(arguments))
