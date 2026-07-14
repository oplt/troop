from backend.modules.orchestration.constants import TASK_TRANSITIONS
from backend.modules.orchestration.schemas import TaskCreate, TaskUpdate
from backend.modules.projects.tasks_service import OrchestrationTasksServiceMixin


def test_task_contract_exposes_workflow_fields_and_external_evidence() -> None:
    payload = TaskCreate(
        title="Implement task orchestration",
        required_tools=[" fs_read ", "code_execute", "fs_read"],
        external_links=[{"kind": "issue", "label": "Planning issue", "url": "https://github.com/acme/repo/issues/42"}],
    )

    assert payload.required_tools == ["fs_read", "code_execute", "fs_read"]
    assert payload.external_links[0]["kind"] == "issue"
    assert "required_tools" in TaskUpdate.model_fields
    assert "external_links" in TaskUpdate.model_fields


def test_task_metadata_normalizes_tools_and_external_links() -> None:
    metadata = OrchestrationTasksServiceMixin()._normalized_task_metadata(
        {
            "required_tools": "legacy_tool",
            "external_links": [{"kind": "not-a-kind", "label": "", "url": ""}],
        },
        required_tools=["fs_read", " fs_read ", "code_execute"],
        external_links=[
            {"kind": "issue", "label": "Issue", "url": " https://example.test/issue "},
            {
                "kind": "invalid",
                "label": "Docs",
                "url": "https://example.test/docs",
                "notes": " context ",
            },
        ],
    )

    assert metadata["required_tools"] == ["fs_read", "code_execute"]
    assert [link["kind"] for link in metadata["external_links"]] == ["issue", "other"]
    assert metadata["external_links"][0]["url"] == "https://example.test/issue"
    assert metadata["external_links"][1]["notes"] == "context"
    assert metadata["evidence_bundle"]["accepted_artifact_ids"] == []


def test_task_state_machine_supports_review_reopen_sync_and_archive_paths() -> None:
    assert "needs_review" in TASK_TRANSITIONS["in_progress"]
    assert "planned" in TASK_TRANSITIONS["needs_review"]
    assert "synced_to_github" in TASK_TRANSITIONS["completed"]
    assert "archived" in TASK_TRANSITIONS["synced_to_github"]
