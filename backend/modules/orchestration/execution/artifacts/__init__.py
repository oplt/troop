"""Execution run artifact persistence."""

from backend.modules.orchestration.execution.artifacts.evidence import (
    ExecutionArtifactsEvidenceMixin,
)
from backend.modules.orchestration.execution.artifacts.publisher import (
    ExecutionArtifactsPublisherMixin,
)


class ExecutionArtifactsMixin(
    ExecutionArtifactsPublisherMixin,
    ExecutionArtifactsEvidenceMixin,
):
    """Publish final bundles and persist run artifacts."""
