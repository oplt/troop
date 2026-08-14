"""Natural-language workflow scaffold generation (PROD-002)."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.orchestration.models import ProviderConfig
from backend.modules.orchestration.providers import execute_prompt
from backend.modules.workforce.connectors.manifest import ConnectorManifest, OperationKind
from backend.modules.workforce.connectors.registry import ConnectorManifestRegistry
from backend.modules.workforce.models import ConnectorDefinition, ConnectorInstallation, WorkflowDefinition
from backend.modules.workforce.services.connector_service import ConnectorService
from backend.modules.workforce.services.workflow_scaffold_validator import (
    WorkflowScaffoldValidator,
    trigger_type_for_operation_slug,
)
from backend.modules.workforce.services.workflow_version_service import WorkflowVersionService


def _normalize_slug(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9-]+", "-", value.strip().lower()).strip("-")
    return cleaned[:255] or "generated-workflow"


def _slug_from_prompt(prompt: str) -> str:
    base = _normalize_slug(prompt)[:48] or "generated-workflow"
    return f"{base}-{uuid4().hex[:6]}"


def _node(
    node_id: str,
    ntype: str,
    label: str,
    config: dict[str, Any] | None = None,
    *,
    x: int = 120,
    y: int = 80,
) -> dict[str, Any]:
    return {
        "id": node_id,
        "type": ntype,
        "label": label,
        "config": dict(config or {}),
        "position": {"x": x, "y": y},
    }


def _edge(source: str, target: str, *, label: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": f"edge_{source}_{target}",
        "from": source,
        "to": target,
    }
    if label:
        payload["label"] = label
    return payload


def _catalog_snapshot_hash(catalog: dict[str, Any]) -> str:
    canonical = json.dumps(catalog, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def _heuristic_generate(
    *,
    prompt: str,
    catalog: dict[str, Any],
    installations_by_provider: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    lowered = prompt.lower()
    installed = set(catalog.get("installed_providers") or [])
    operations = {
        str(item.get("slug")): item for item in catalog.get("operations") or [] if item.get("slug")
    }

    def has_op(slug: str) -> bool:
        return slug in operations

    def installation_for(provider: str) -> str | None:
        item = installations_by_provider.get(provider)
        return str(item.get("id")) if item else None

    if "gmail" in lowered or "email" in lowered or "inbox" in lowered:
        if "gmail" not in installed or not has_op("gmail.new_message"):
            return _manual_agent_starter(prompt, catalog)

        gmail_id = installation_for("gmail")
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []
        trigger_cfg: dict[str, Any] = {
            "trigger_type": "gmail_new_message",
            "event_type": "gmail_new_message",
        }
        if gmail_id:
            trigger_cfg["connector_installation_id"] = gmail_id

        specs: list[tuple[str, str, str, dict[str, Any]]] = [
            ("trigger", "trigger", "Gmail: new email", trigger_cfg),
            ("fetch_thread", "tool", "Fetch Gmail thread", {"tool_slug": "gmail.get_thread", "tool": "gmail.get_thread"}),
            ("triage", "agent", "Classify incoming email", {"input_mapping": "$.email"}),
            ("should_reply", "condition", "Reply required?", {"expression": "$.triage.should_reply == true"}),
            ("draft_reply", "agent", "Draft response", {"input_mapping": "$.thread"}),
        ]
        if has_op("gmail.create_draft"):
            specs.append(
                (
                    "create_draft",
                    "tool",
                    "Create Gmail draft",
                    {"tool_slug": "gmail.create_draft", "tool": "gmail.create_draft"},
                )
            )
        if has_op("gmail.send_draft"):
            specs.append(
                ("approve_send", "approval", "Approve before send", {"action": "gmail.send_draft"}),
            )
            specs.append(
                (
                    "send_draft",
                    "tool",
                    "Send approved draft",
                    {"tool_slug": "gmail.send_draft", "tool": "gmail.send_draft"},
                ),
            )

        for index, (node_id, ntype, label, config) in enumerate(specs):
            node_config = dict(config)
            if ntype in {"trigger", "tool"} and gmail_id:
                node_config.setdefault("connector_installation_id", gmail_id)
            nodes.append(_node(node_id, ntype, label, node_config, y=index * 120))

        for index in range(len(nodes) - 1):
            source = str(nodes[index]["id"])
            target = str(nodes[index + 1]["id"])
            edges.append(
                _edge(source, target, label="true" if source == "should_reply" else None)
            )

        return {
            "suggested_name": "Email triage and reply",
            "summary": "Gmail trigger → classify → draft → approval → send using installed Gmail connector.",
            "nodes": nodes,
            "edges": edges,
            "entry_node_id": "trigger",
        }

    if "slack" in lowered and "slack" in installed and has_op("slack.post_message"):
        slack_id = installation_for("slack")
        nodes = [
            _node("trigger", "trigger", "Manual start", {"trigger_type": "manual", "event_type": "manual"}, y=0),
            _node(
                "draft",
                "agent",
                "Draft Slack update",
                {"input_mapping": "$.input"},
                y=120,
            ),
            _node(
                "post",
                "tool",
                "Post to Slack",
                {
                    "tool_slug": "slack.post_message",
                    "tool": "slack.post_message",
                    **({"connector_installation_id": slack_id} if slack_id else {}),
                },
                y=240,
            ),
        ]
        if has_op("slack.post_message"):
            nodes.insert(2, _node("approve", "approval", "Approve Slack message", {"action": "slack.post_message"}, y=180))
            nodes[-1]["position"]["y"] = 300
        edges = [_edge("trigger", "draft"), _edge("draft", "approve" if len(nodes) == 4 else "post")]
        if len(nodes) == 4:
            edges.append(_edge("approve", "post"))
        return {
            "suggested_name": "Slack announcement",
            "summary": "Manual trigger → agent draft → approval → Slack post.",
            "nodes": nodes,
            "edges": edges,
            "entry_node_id": "trigger",
        }

    return _manual_agent_starter(prompt, catalog)


def _manual_agent_starter(prompt: str, catalog: dict[str, Any]) -> dict[str, Any]:
    first_op = next(iter(catalog.get("operations") or []), None)
    nodes = [
        _node("trigger", "trigger", "Manual start", {"trigger_type": "manual", "event_type": "manual"}, y=0),
        _node(
            "agent",
            "agent",
            "Process request",
            {"input_mapping": "$.input", "instructions": prompt[:500]},
            y=120,
        ),
    ]
    edges = [_edge("trigger", "agent")]
    summary = "Manual trigger with an agent step. Connect integrations and extend the graph as needed."
    if first_op:
        summary = (
            f"Starter graph for: {prompt[:120]}. "
            f"Installed connectors include {', '.join(catalog.get('installed_providers') or [])}."
        )
    return {
        "suggested_name": prompt.strip()[:60].title() or "Generated workflow",
        "summary": summary,
        "nodes": nodes,
        "edges": edges,
        "entry_node_id": "trigger",
    }


class WorkflowScaffoldService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.connectors = ConnectorService(db)
        self.version_service = WorkflowVersionService(db)

    async def _load_installation_context(
        self,
        owner_id: str,
    ) -> tuple[
        dict[str, dict[str, Any]],
        dict[str, ConnectorManifest],
    ]:
        installations = await self.connectors.list_installations(owner_id)
        definition_ids = {item.connector_definition_id for item in installations}
        definitions: dict[str, ConnectorDefinition] = {}
        if definition_ids:
            result = await self.db.execute(
                select(ConnectorDefinition).where(ConnectorDefinition.id.in_(definition_ids))
            )
            definitions = {row.id: row for row in result.scalars().all()}

        installations_by_provider: dict[str, dict[str, Any]] = {}
        manifests_by_provider: dict[str, ConnectorManifest] = {}
        for installation in installations:
            definition = definitions.get(installation.connector_definition_id)
            if definition is None:
                continue
            provider_slug = definition.slug
            config = dict(installation.config_json or {})
            installations_by_provider[provider_slug] = {
                "id": installation.id,
                "name": installation.name,
                "status": installation.status,
                "granted_scopes": list(config.get("granted_scopes") or []),
            }
            manifest = ConnectorManifestRegistry.get_manifest(provider_slug)
            if manifest is not None:
                manifests_by_provider[provider_slug] = manifest

        return installations_by_provider, manifests_by_provider

    def _build_catalog(
        self,
        *,
        manifests_by_provider: dict[str, ConnectorManifest],
        installations_by_provider: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        operations: list[dict[str, Any]] = []
        for provider_slug, manifest in sorted(manifests_by_provider.items()):
            if provider_slug not in installations_by_provider:
                continue
            for operation in manifest.all_operations():
                operations.append(
                    {
                        "provider_slug": provider_slug,
                        "slug": operation.slug,
                        "name": operation.name,
                        "operation_kind": operation.operation_kind.value,
                        "requires_approval": operation.requires_approval,
                        "required_scopes": list(operation.required_scopes),
                        "risk_level": operation.risk_level,
                    }
                )
        return {
            "installed_providers": sorted(installations_by_provider.keys()),
            "operations": operations,
        }

    async def generate(
        self,
        *,
        owner_id: str,
        prompt: str,
        workflow_id: str | None = None,
        name: str | None = None,
        slug: str | None = None,
        company_id: str | None = None,
        use_llm: bool = True,
        provider: ProviderConfig | None = None,
        model_name: str | None = None,
    ) -> dict[str, Any]:
        installations_by_provider, manifests_by_provider = await self._load_installation_context(
            owner_id
        )
        catalog = self._build_catalog(
            manifests_by_provider=manifests_by_provider,
            installations_by_provider=installations_by_provider,
        )
        allowed_operation_slugs = {str(item["slug"]) for item in catalog["operations"]}
        catalog_hash = _catalog_snapshot_hash(catalog)

        generation_mode = "heuristic"
        model_used: str | None = None
        if use_llm and provider:
            try:
                graph_data = await self._llm_generate(
                    prompt=prompt,
                    catalog=catalog,
                    provider=provider,
                    model_name=model_name,
                )
                generation_mode = "llm"
                model_used = model_name or provider.default_model
            except Exception:
                graph_data = _heuristic_generate(
                    prompt=prompt,
                    catalog=catalog,
                    installations_by_provider=installations_by_provider,
                )
        else:
            graph_data = _heuristic_generate(
                prompt=prompt,
                catalog=catalog,
                installations_by_provider=installations_by_provider,
            )

        nodes = list(graph_data.get("nodes") or [])
        edges = list(graph_data.get("edges") or [])
        entry_node_id = graph_data.get("entry_node_id")
        suggested_name = str(graph_data.get("suggested_name") or name or prompt[:60].title())
        summary = str(graph_data.get("summary") or "Generated workflow draft.")

        nodes, edges, entry_node_id = self._sanitize_generated_graph(
            nodes=nodes,
            edges=edges,
            entry_node_id=entry_node_id,
            allowed_operation_slugs=allowed_operation_slugs,
            installations_by_provider=installations_by_provider,
            manifests_by_provider=manifests_by_provider,
        )

        validator = WorkflowScaffoldValidator(
            allowed_operation_slugs=allowed_operation_slugs,
            manifests_by_provider=manifests_by_provider,
            installations_by_provider=installations_by_provider,
        )
        validation = validator.validate_graph(
            nodes=nodes,
            edges=edges,
            entry_node_id=entry_node_id,
            db=self.db,
        )
        gaps = list(validation.pop("gaps", []))

        provenance_payload = {
            "source": "nl_scaffold",
            "prompt": prompt,
            "model": model_used,
            "generated_at": datetime.now(UTC).isoformat(),
            "catalog_snapshot_hash": catalog_hash,
            "generation_mode": generation_mode,
        }

        definition, draft = await self._persist_draft(
            owner_id=owner_id,
            workflow_id=workflow_id,
            name=suggested_name if not name else name,
            slug=slug or _slug_from_prompt(prompt),
            company_id=company_id,
            nodes=nodes,
            edges=edges,
            entry_node_id=entry_node_id,
            provenance=provenance_payload,
        )

        return {
            "workflow_id": definition.id,
            "name": definition.name,
            "slug": definition.slug,
            "summary": summary,
            "draft": {
                "nodes": nodes,
                "edges": edges,
                "entry_node_id": entry_node_id,
            },
            "validation": validation,
            "gaps": gaps,
            "provenance": provenance_payload,
            "published": False,
        }

    def _sanitize_generated_graph(
        self,
        *,
        nodes: list[Any],
        edges: list[Any],
        entry_node_id: str | None,
        allowed_operation_slugs: set[str],
        installations_by_provider: dict[str, dict[str, Any]],
        manifests_by_provider: dict[str, ConnectorManifest],
    ) -> tuple[list[Any], list[Any], str | None]:
        sanitized_nodes: list[Any] = []
        for index, node in enumerate(nodes):
            if not isinstance(node, dict):
                continue
            node_id = str(node.get("id") or f"node_{index + 1}")
            ntype = str(node.get("type") or "tool")
            config = dict(node.get("config") or {})
            label = str(node.get("label") or ntype.replace("_", " "))
            position = node.get("position") if isinstance(node.get("position"), dict) else {}
            x = int(position.get("x") or 120 + (index % 3) * 260)
            y = int(position.get("y") or 80 + (index // 3) * 160)

            if ntype == "trigger":
                trigger_type = str(
                    config.get("trigger_type") or config.get("event_type") or "manual"
                )
                operation_slug = trigger_type.replace("_", ".")
                if operation_slug in allowed_operation_slugs:
                    config["trigger_type"] = trigger_type_for_operation_slug(operation_slug)
                    config["event_type"] = config["trigger_type"]
                    provider = self._provider_for_slug(operation_slug, manifests_by_provider)
                    if provider:
                        installation = installations_by_provider.get(provider)
                        if installation and not config.get("connector_installation_id"):
                            config["connector_installation_id"] = installation["id"]

            if ntype == "tool":
                operation_slug = str(
                    config.get("tool") or config.get("tool_slug") or config.get("operation") or ""
                ).strip()
                if operation_slug and operation_slug not in allowed_operation_slugs:
                    continue
                if operation_slug:
                    config["tool"] = operation_slug
                    config["tool_slug"] = operation_slug
                    config["operation"] = operation_slug
                    provider = self._provider_for_slug(operation_slug, manifests_by_provider)
                    if provider:
                        installation = installations_by_provider.get(provider)
                        if installation and not config.get("connector_installation_id"):
                            config["connector_installation_id"] = installation["id"]

            sanitized_nodes.append(
                {
                    "id": node_id,
                    "type": ntype,
                    "label": label,
                    "config": config,
                    "position": {"x": x, "y": y},
                }
            )

        valid_ids = {str(node["id"]) for node in sanitized_nodes}
        sanitized_edges: list[Any] = []
        for index, edge in enumerate(edges):
            if not isinstance(edge, dict):
                continue
            source = str(edge.get("from") or edge.get("source") or "")
            target = str(edge.get("to") or edge.get("target") or "")
            if source not in valid_ids or target not in valid_ids:
                continue
            sanitized_edges.append(
                {
                    "id": str(edge.get("id") or f"edge_{source}_{target}_{index}"),
                    "from": source,
                    "to": target,
                    **({"label": edge["label"]} if edge.get("label") else {}),
                }
            )

        entry = str(entry_node_id or "")
        if entry not in valid_ids:
            trigger = next(
                (str(node["id"]) for node in sanitized_nodes if node.get("type") == "trigger"),
                None,
            )
            entry = trigger or (str(sanitized_nodes[0]["id"]) if sanitized_nodes else "")

        return sanitized_nodes, sanitized_edges, entry or None

    @staticmethod
    def _provider_for_slug(
        operation_slug: str,
        manifests_by_provider: dict[str, ConnectorManifest],
    ) -> str | None:
        for provider_slug, manifest in manifests_by_provider.items():
            if manifest.get_operation(operation_slug) is not None:
                return provider_slug
        if "." in operation_slug:
            return operation_slug.split(".", 1)[0]
        return None

    async def _persist_draft(
        self,
        *,
        owner_id: str,
        workflow_id: str | None,
        name: str,
        slug: str,
        company_id: str | None,
        nodes: list[Any],
        edges: list[Any],
        entry_node_id: str | None,
        provenance: dict[str, Any],
    ) -> tuple[WorkflowDefinition, Any]:
        if workflow_id:
            definition = await self.db.get(WorkflowDefinition, workflow_id)
            if definition is None or definition.owner_id != owner_id:
                raise ValueError("workflow not found")
            draft = await self.version_service.update_draft(
                definition,
                nodes=nodes,
                edges=edges,
                entry_node_id=entry_node_id,
                actor_user_id=owner_id,
            )
            definition.name = name
            definition.status = "draft"
        else:
            definition = WorkflowDefinition(
                id=str(uuid4()),
                owner_id=owner_id,
                company_id=company_id,
                slug=_normalize_slug(slug),
                name=name.strip() or "Generated workflow",
                description=f"Generated from prompt: {provenance.get('prompt', '')[:240]}",
                category="general",
                status="draft",
                is_template=False,
            )
            self.db.add(definition)
            await self.db.flush()
            draft = await self.version_service.ensure_draft(
                definition,
                created_by=owner_id,
                nodes=nodes,
                edges=edges,
                entry_node_id=entry_node_id,
            )

        draft.metadata_json = {
            **(draft.metadata_json or {}),
            "kind": "draft",
            **provenance,
        }
        await self.db.flush()
        return definition, draft

    async def _llm_generate(
        self,
        *,
        prompt: str,
        catalog: dict[str, Any],
        provider: ProviderConfig,
        model_name: str | None,
    ) -> dict[str, Any]:
        operations = catalog.get("operations") or []
        catalog_lines = "\n".join(
            f"- {item['slug']} ({item['operation_kind']}, approval={item['requires_approval']})"
            for item in operations[:80]
        )
        system_prompt = """You design workforce workflow graphs as JSON only.

Rules:
- Use ONLY operation slugs from the installed connector catalog for trigger/tool nodes.
- Never invent tools, providers, or OAuth scopes.
- Include approval nodes before external writes that require approval.
- Use node types: trigger, agent, skill, tool, condition, router, parallel, approval, human_input, delay, subworkflow.
- For Gmail triggers use trigger_type "gmail_new_message". For Outlook use "outlook_new_message".
- For connector tool nodes set config.tool_slug to the catalog slug (e.g. gmail.get_thread).
- Do not include connector_installation_id; the server binds installations when available.
- Return valid JSON matching the schema exactly."""

        user_prompt = f"""User goal:
{prompt}

Installed connector catalog:
{catalog_lines or "(no connectors installed — use manual trigger and agent nodes only)"}

Return JSON:
{{
  "suggested_name": "string",
  "summary": "string",
  "entry_node_id": "string",
  "nodes": [
    {{
      "id": "string",
      "type": "trigger|agent|tool|condition|approval|...",
      "label": "string",
      "config": {{}}
    }}
  ],
  "edges": [{{ "from": "node_id", "to": "node_id", "label": "optional" }}]
}}"""

        result = await execute_prompt(
            provider,
            model_name=model_name,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_format="json",
            request_options={"structured_output": True},
        )
        data = result.output_json or json.loads(result.output_text)
        if not isinstance(data, dict):
            raise ValueError("LLM scaffold response must be an object")
        return data
