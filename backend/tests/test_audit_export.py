"""Tests for enterprise audit export (ENT-001)."""

from __future__ import annotations

from datetime import UTC, datetime

from backend.modules.audit.export_service import AuditExportService
from backend.modules.audit.models import AuditLog


def test_audit_export_csv_and_ndjson() -> None:
    rows = [
        {
            "id": "log-1",
            "created_at": "2026-08-14T12:00:00+00:00",
            "action": "auth.sign_in",
            "user_id": "user-1",
            "workspace_id": None,
            "resource_type": None,
            "resource_id": None,
            "ip_address": "127.0.0.1",
            "metadata": {"method": "password"},
        }
    ]
    ndjson = AuditExportService.to_ndjson(rows)
    csv = AuditExportService.to_csv(rows)
    assert '"auth.sign_in"' in ndjson
    assert "auth.sign_in" in csv


def test_audit_log_to_dict_parses_metadata() -> None:
    from backend.modules.audit.export_service import audit_log_to_dict

    log = AuditLog(
        id="log-1",
        user_id="user-1",
        action="admin.audit_export",
        metadata_json='{"format":"ndjson","row_count":3}',
        created_at=datetime.now(UTC),
    )
    payload = audit_log_to_dict(log)
    assert payload["metadata"]["format"] == "ndjson"
