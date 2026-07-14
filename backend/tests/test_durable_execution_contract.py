from __future__ import annotations

from unittest.mock import patch

import pytest
from backend.core.config import settings
from backend.modules.orchestration.execution.durable_execution import (
    durable_backend_status,
    submit_orchestration_run,
)


def test_celery_backend_reports_delivery_and_checkpoint_contract():
    status = durable_backend_status()

    assert status["configured"] == "celery"
    assert status["active"] == "celery"
    assert status["available"] is True
    assert status["delivery"] == "at_least_once"
    assert status["checkpointed"] is True


def test_unsupported_durable_backend_fails_closed_before_enqueue():
    with (
        patch.object(settings, "ORCHESTRATION_DURABLE_QUEUE_BACKEND", "temporal"),
        pytest.raises(RuntimeError, match="configured but unavailable"),
    ):
        submit_orchestration_run("run-unsupported")
