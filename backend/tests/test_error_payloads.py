from backend.core.error_payloads import error_payload


def test_error_payload_preserves_legacy_detail_and_structured_error() -> None:
    payload = error_payload(
        code="BAD_REQUEST",
        message="Invalid input",
        correlation_id="corr-1",
        details={"field": "name"},
    )

    assert payload["detail"] == "Invalid input"
    assert payload["correlation_id"] == "corr-1"
    assert payload["error"] == {
        "code": "BAD_REQUEST",
        "message": "Invalid input",
        "details": {"field": "name"},
    }
