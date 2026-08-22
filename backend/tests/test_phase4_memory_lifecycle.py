from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from backend.modules.memory.compaction import prune_checkpoint_after_compaction
from backend.modules.memory.context_retrieval_planner import ContextRetrievalPlanner
from backend.modules.memory.evaluation import evaluate_memory_regression
from backend.modules.memory.layer.provider import SemanticMemoryProvider
from backend.modules.memory.promotion_rules import PromotionCandidate, evaluate
from backend.modules.memory.retrieval_scoping import staged_semantic_vector_retrieval
from backend.modules.memory.working_memory import WORKING_MEMORY_KEY


def _candidate(
    planner: ContextRetrievalPlanner,
    source_id: str,
    *,
    scope: str = "project",
    project_id: str | None = "project-1",
    company_id: str | None = None,
    canonical_key: str | None = None,
    entry_type: str = "fact",
    authority: float = 0.6,
    relevance: float = 0.8,
    status: str = "current",
    valid_until: datetime | None = None,
):
    return planner.candidate(
        kind="semantic_memory",
        scope=scope,
        content=f"Memory content {source_id}",
        relevance=relevance,
        authority=authority,
        confidence=0.8,
        provenance={
            "owner_id": "owner-1",
            "project_id": project_id,
            "company_id": company_id,
            "entry_type": entry_type,
        },
        source_id=source_id,
        canonical_key=canonical_key,
        status=status,
        valid_until=valid_until,
    )


def test_company_policy_wins_same_canonical_fact():
    planner = ContextRetrievalPlanner(
        owner_id="owner-1",
        project_id="project-1",
        company_id="company-1",
    )
    project_observation = _candidate(
        planner,
        "project-observation",
        canonical_key="data/residency",
        relevance=1.0,
    )
    company_policy = _candidate(
        planner,
        "company-policy",
        scope="company",
        project_id=None,
        company_id="company-1",
        canonical_key="data/residency",
        entry_type="policy",
        authority=1.0,
        relevance=0.4,
    )

    selected = planner.select([project_observation, company_policy], max_tokens=500)

    assert [item.source_id for item in selected] == ["company-policy"]


def test_planner_rejects_stale_superseded_and_cross_project_memory():
    planner = ContextRetrievalPlanner(owner_id="owner-1", project_id="project-1")
    selected = planner.select(
        [
            _candidate(planner, "valid"),
            _candidate(planner, "superseded", status="superseded"),
            _candidate(
                planner,
                "expired",
                valid_until=datetime.now(UTC) - timedelta(seconds=1),
            ),
            _candidate(planner, "cross-project", project_id="project-2"),
        ],
        max_tokens=500,
    )

    assert [item.source_id for item in selected] == ["valid"]


@pytest.mark.asyncio
async def test_semantic_provider_supersedes_prior_canonical_version():
    now = datetime.now(UTC)
    prior = SimpleNamespace(id="memory-v1", status="current", valid_until=None, memory_version=2)
    repository = MagicMock()
    repository.find_current_by_canonical_key = AsyncMock(return_value=prior)
    repository.update = AsyncMock(side_effect=lambda row: row)
    repository.enqueue_embedding = AsyncMock()

    async def create(**kwargs):
        return SimpleNamespace(
            id="memory-v2",
            body=kwargs["body"],
            owner_id=kwargs["owner_id"],
            title=kwargs["title"],
            entry_type=kwargs["entry_type"],
            scope=kwargs["scope"],
            project_id=kwargs["project_id"],
            company_id=kwargs["company_id"],
            agent_id=kwargs["agent_id"],
            source_run_id=kwargs["source_run_id"],
            source_task_id=kwargs["source_task_id"],
            source_chunk_id=kwargs["source_chunk_id"],
            metadata_json=kwargs["metadata_json"],
            provenance_json=kwargs["provenance_json"],
            created_at=now,
            updated_at=now,
            deleted_at=None,
            **{
                key: kwargs[key]
                for key in (
                    "ttl_days",
                    "expires_at",
                    "retention_policy",
                    "memory_version",
                    "canonical_key",
                    "valid_from",
                    "valid_until",
                    "status",
                    "supersedes_memory_id",
                    "embedding_model",
                    "embedding_version",
                )
            },
        )

    repository.create = AsyncMock(side_effect=create)
    provider = SemanticMemoryProvider(repository)
    record = await provider.add(
        owner_id="owner-1",
        content="Deadline moved to 18 September",
        scope="project",
        project_id="project-1",
        metadata={
            "entry_type": "fact",
            "title": "Project deadline",
            "canonical_key": "project/project-1/deadline",
        },
    )

    assert prior.status == "superseded"
    assert prior.valid_until is not None
    assert record.memory_version == 3
    assert record.supersedes_memory_id == "memory-v1"
    assert record.status == "current"


def test_promotion_policy_formalizes_auto_review_and_never_boundaries():
    approved_decision = evaluate(
        PromotionCandidate(
            entry_type="decision",
            title="Approved architecture choice",
            body="Use the event queue for durable orchestration outcomes.",
            source="project_decision",
            metadata={"approved": True},
        )
    )
    company_policy = evaluate(
        PromotionCandidate(
            entry_type="policy",
            title="Company security policy",
            body="All customer data must remain inside the EU for compliance.",
            source="classifier",
            scope="company",
        )
    )
    transient = evaluate(
        PromotionCandidate(
            entry_type="note",
            title="Temporary timeout",
            body="The tool failed once during a transient provider outage.",
            source="temporary_tool_error",
        )
    )

    assert approved_decision.verdict == "auto"
    assert company_policy.verdict == "suggest"
    assert transient.verdict == "skip"


@pytest.mark.asyncio
async def test_staged_semantic_retrieval_always_checks_company_policy():
    repo = MagicMock()
    repo.search_semantic_memory_by_vector_scoped = AsyncMock(
        return_value=[SimpleNamespace(id="task")]
    )
    repo.search_semantic_memory_by_vector = AsyncMock(return_value=[])
    repo.search_semantic_memory_by_vector_company = AsyncMock(
        return_value=[SimpleNamespace(id="company-policy")]
    )
    repo.list_related_project_ids_for_retrieval = AsyncMock(return_value=[])

    rows, _ = await staged_semantic_vector_retrieval(
        repo,
        owner_id="owner-1",
        project_id="project-1",
        task_id="task-1",
        company_id="company-1",
        agent_id=None,
        query_vec=[0.1, 0.2],
        min_hits=1,
        per_stage_limit=4,
        related_project_limit=2,
    )

    assert [row.id for row in rows] == ["task", "company-policy"]
    repo.search_semantic_memory_by_vector_company.assert_awaited_once()


def test_memory_regression_metrics_and_task_close_compaction():
    planner = ContextRetrievalPlanner(owner_id="owner-1", project_id="project-1")
    selected = [_candidate(planner, "useful")]
    supported = evaluate(
        PromotionCandidate(
            entry_type="decision",
            title="Approved decision",
            body="Use one durable queue for all orchestration outcomes.",
            source="project_decision",
            metadata={"approved": True},
        )
    )
    report = evaluate_memory_regression(
        selected,
        useful_source_ids={"useful"},
        owner_id="owner-1",
        project_id="project-1",
        promotion_results=[(supported, True)],
    )
    compacted = prune_checkpoint_after_compaction(
        {
            "working_memory": {
                "objective": "Ship safely",
                "accepted_plan": "Very long plan",
                "latest_findings": "Verified result",
                "temp_notes": "Transient notes",
            },
            "workflow": {"resume_count": 2},
        }
    )

    assert report.passed
    assert report.retrieval_precision == 1.0
    assert compacted[WORKING_MEMORY_KEY]["compacted"] is True
    assert compacted[WORKING_MEMORY_KEY]["temp_notes"] == ""
    assert compacted["workflow"] == {"resume_count": 2}
