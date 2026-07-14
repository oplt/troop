import pytest
from pydantic import ValidationError

from backend.modules.orchestration.schemas import AgentMemoryEntryCreate
from backend.modules.memory.settings import merge_memory_settings


def test_agent_memory_write_contract_supports_expiry_and_long_term_scope() -> None:
    payload = AgentMemoryEntryCreate(
        agent_id="agent-1",
        key="preferred_style",
        value_text="Use concise implementation notes with evidence.",
        scope="long-term",
        ttl_days=180,
    )

    assert payload.scope == "long-term"
    assert payload.ttl_days == 180


def test_agent_memory_write_contract_rejects_unbounded_ttl() -> None:
    with pytest.raises(ValidationError):
        AgentMemoryEntryCreate(
            agent_id="agent-1",
            key="style",
            value_text="Concise",
            ttl_days=3651,
        )


def test_memory_defaults_keep_all_layers_enabled() -> None:
    settings = merge_memory_settings(None)

    assert settings["memory_layer_enabled"] is True
    assert settings["layer"]["enabled"] is True
    assert settings["episodic_archive_enabled"] is True
    assert settings["semantic_write_requires_approval"] is False
