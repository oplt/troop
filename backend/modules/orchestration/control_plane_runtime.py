from __future__ import annotations

from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from backend.modules.orchestration.models import ModelCapability, ProviderConfig
from backend.modules.team.models import AgentProfile, SkillPack


class RuntimeToolBinding(BaseModel):
    slug: str
    source: str
    description: str


class RuntimeModelProfile(BaseModel):
    provider_id: str | None = None
    provider_name: str | None = None
    provider_type: str | None = None
    model_slug: str | None = None
    fallback_model_slug: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    supports_tools: bool = False
    supports_structured_output: bool = False
    max_context_tokens: int | None = None


class RuntimeStructuredOperation(BaseModel):
    name: str
    description: str
    output_schema: dict[str, Any] = Field(default_factory=dict)
    prompt_messages: list[dict[str, str]] = Field(default_factory=list)


class AgentRuntimeProfile(BaseModel):
    agent_id: str
    agent_name: str
    role: str
    identity: dict[str, Any] = Field(default_factory=dict)
    instruction_stack: list[str] = Field(default_factory=list)
    memory_policy: dict[str, Any] = Field(default_factory=dict)
    tool_policy: dict[str, Any] = Field(default_factory=dict)
    primary_model: RuntimeModelProfile = Field(default_factory=RuntimeModelProfile)
    fallback_model: RuntimeModelProfile | None = None
    routing_policy: dict[str, Any] = Field(default_factory=dict)
    structured_operations: list[RuntimeStructuredOperation] = Field(default_factory=list)
    langchain_backend: dict[str, Any] = Field(
        default_factory=lambda: {
            "prompt_template": "ChatPromptTemplate",
            "execution_layer": "langchain-core",
            "structured_output_mode": "pydantic-json",
        }
    )


class ManagerPlanningOutput(BaseModel):
    summary: str
    goals: list[str] = Field(default_factory=list)
    tasks: list[dict[str, Any]] = Field(default_factory=list)
    review_points: list[str] = Field(default_factory=list)


class TaskAssignmentOutput(BaseModel):
    assignee_agent_id: str
    rationale: str
    execution_notes: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)


class QAReviewOutput(BaseModel):
    verdict: str
    rationale: str
    required_revisions: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)


class RevisionRequestOutput(BaseModel):
    revision_summary: str
    requested_changes: list[str] = Field(default_factory=list)
    blocking_reasons: list[str] = Field(default_factory=list)


def _skill_map(skills: list[SkillPack]) -> dict[str, SkillPack]:
    return {item.slug: item for item in skills}


def _resolve_model_capability(
    model_slug: str | None,
    capabilities: list[ModelCapability],
) -> ModelCapability | None:
    if not model_slug:
        return None
    for item in capabilities:
        if item.model_slug == model_slug:
            return item
    return None


def _runtime_model_profile(
    provider: ProviderConfig | None,
    model_slug: str | None,
    fallback_model_slug: str | None,
    capabilities: list[ModelCapability],
) -> RuntimeModelProfile:
    model_capability = _resolve_model_capability(model_slug, capabilities)
    return RuntimeModelProfile(
        provider_id=provider.id if provider else None,
        provider_name=provider.name if provider else None,
        provider_type=provider.provider_type if provider else None,
        model_slug=model_slug,
        fallback_model_slug=fallback_model_slug,
        temperature=provider.temperature if provider else None,
        max_tokens=provider.max_tokens if provider else None,
        supports_tools=bool(model_capability.supports_tools) if model_capability else False,
        supports_structured_output=bool(
            (model_capability.metadata_json or {}).get("supports_structured_output", model_capability.supports_tools)
        )
        if model_capability
        else False,
        max_context_tokens=model_capability.max_context_tokens if model_capability else None,
    )


def _prompt_messages(system_prompt: str, human_prompt: str) -> list[dict[str, str]]:
    ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            ("human", human_prompt),
        ]
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "human", "content": human_prompt},
    ]


def _operation(
    *,
    name: str,
    description: str,
    schema: type[BaseModel],
    role_prompt: str,
) -> RuntimeStructuredOperation:
    return RuntimeStructuredOperation(
        name=name,
        description=description,
        output_schema=schema.model_json_schema(),
        prompt_messages=_prompt_messages(
            "Return valid JSON matching requested schema. Keep reasoning concise and actionable.",
            role_prompt,
        ),
    )


def build_agent_runtime_profile(
    agent: AgentProfile,
    *,
    provider: ProviderConfig | None,
    model_capabilities: list[ModelCapability],
    skills: list[SkillPack],
) -> AgentRuntimeProfile:
    model_policy = dict(agent.model_policy_json or {})
    memory_policy = dict(agent.memory_policy_json or {})
    metadata = dict(agent.metadata_json or {})
    skill_lookup = _skill_map(skills)
    resolved_skills = [skill_lookup[item] for item in agent.skills_json if item in skill_lookup]

    instruction_stack = [
        line
        for line in [
            agent.system_prompt.strip(),
            agent.mission_markdown.strip(),
            agent.rules_markdown.strip(),
            *[item.rules_markdown.strip() for item in resolved_skills if item.rules_markdown.strip()],
        ]
        if line
    ]

    tool_bindings = [
        RuntimeToolBinding(
            slug=tool_slug,
            source="skill" if any(tool_slug in item.allowed_tools_json for item in resolved_skills) else "agent",
            description=f"Allowed tool `{tool_slug}` for role execution.",
        )
        for tool_slug in agent.allowed_tools_json
    ]

    primary_model_slug = str(model_policy.get("model") or provider.default_model if provider else model_policy.get("model") or "")
    fallback_model_slug = str(
        model_policy.get("fallback_model") or provider.fallback_model if provider else model_policy.get("fallback_model") or ""
    )
    primary_profile = _runtime_model_profile(
        provider,
        primary_model_slug or None,
        fallback_model_slug or None,
        model_capabilities,
    )
    fallback_profile = (
        _runtime_model_profile(provider, fallback_model_slug or None, None, model_capabilities)
        if fallback_model_slug
        else None
    )

    is_manager = "manager" in agent.role.lower()
    operations = [
        _operation(
            name="managerPlanning",
            description="Decompose goals into reviewable tasks and checkpoints.",
            schema=ManagerPlanningOutput,
            role_prompt="Break project goal into bounded tasks with owners, acceptance criteria, and review checkpoints.",
        ),
        _operation(
            name="taskAssignment",
            description="Route work to best-fit agent with rationale.",
            schema=TaskAssignmentOutput,
            role_prompt="Choose best assignee, state why, note execution constraints and risk flags.",
        ),
        _operation(
            name="qaReview",
            description="Evaluate output quality against requirements and evidence.",
            schema=QAReviewOutput,
            role_prompt="Review submitted work, decide verdict, cite evidence, list required revisions if needed.",
        ),
        _operation(
            name="revisionRequest",
            description="Return structured revision request.",
            schema=RevisionRequestOutput,
            role_prompt="Return concise revision request with blocking reasons and concrete changes.",
        ),
    ]
    if not is_manager:
        operations = operations[1:]

    return AgentRuntimeProfile(
        agent_id=agent.id,
        agent_name=agent.name,
        role=agent.role,
        identity={
            "name": agent.name,
            "role": agent.role,
            "objective": metadata.get("objective") or agent.description or agent.mission_markdown,
            "skills": agent.skills_json,
        },
        instruction_stack=instruction_stack,
        memory_policy={
            **memory_policy,
            "scope": metadata.get("memory_scope") or memory_policy.get("scope") or "project",
        },
        tool_policy={
            "allowed_tools": agent.allowed_tools_json,
            "bindings": [item.model_dump() for item in tool_bindings],
        },
        primary_model=primary_profile,
        fallback_model=fallback_profile,
        routing_policy={
            "primary_model_profile": primary_model_slug or None,
            "fallback_model_profile": fallback_model_slug or None,
            "future_routes": model_policy.get("routes", []),
        },
        structured_operations=operations,
    )
