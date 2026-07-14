from backend.modules.orchestration.models import ProviderConfig
from backend.modules.orchestration.providers import (
    _capability_record,
    _request_float,
    _request_int,
)


def test_provider_capability_catalog_exposes_routing_features() -> None:
    provider = ProviderConfig(
        owner_id="owner-1",
        name="Private Ollama",
        provider_type="ollama",
        default_model="llama3.1:8b",
    )

    capability = _capability_record(
        provider,
        model_slug="llama3.1:8b",
        display_name="Llama 3.1 8B",
        supports_tools=True,
        supports_vision=False,
        context_window=8192,
        max_output_tokens=4096,
        input_cost_per_1k=0.0,
        output_cost_per_1k=0.0,
        latency_p50=120,
        health_status="healthy",
        source_for_each_field={},
        source="ollama_api",
    )

    assert capability["supports_tool_calling"] is True
    assert capability["supports_structured_output"] is True
    assert capability["supports_reasoning"] is False


def test_agent_request_options_override_provider_defaults() -> None:
    options = {"max_tokens": "2048", "temperature": "0.7"}

    assert _request_int(options, "max_tokens", 4096) == 2048
    assert _request_float(options, "temperature", 0.2) == 0.7
    assert _request_int({}, "max_tokens", 4096) == 4096
