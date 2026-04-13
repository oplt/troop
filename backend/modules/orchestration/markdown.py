import re
from typing import Any

import yaml

FRONTMATTER_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)
HEADER_PATTERN = re.compile(r"^#\s+(.+)$", re.MULTILINE)


def parse_agent_markdown(content: str) -> tuple[dict[str, Any] | None, list[str]]:
    errors: list[str] = []
    stripped = content.strip()
    if not stripped:
        return None, ["Markdown content is empty."]

    match = FRONTMATTER_PATTERN.match(content)
    if not match:
        return None, ["Markdown frontmatter block is required."]

    raw_frontmatter, body = match.groups()
    try:
        frontmatter = yaml.safe_load(raw_frontmatter) or {}
    except yaml.YAMLError as exc:
        return None, [f"Invalid YAML frontmatter: {exc}"]

    if not isinstance(frontmatter, dict):
        return None, ["Frontmatter must resolve to an object."]

    name = str(frontmatter.get("name", "")).strip()
    slug = str(frontmatter.get("slug", "")).strip() or _slugify(name)
    role = str(frontmatter.get("role", "specialist")).strip() or "specialist"
    version = int(frontmatter.get("version", 1) or 1)
    capabilities = _normalize_string_list(frontmatter.get("capabilities"))
    tools = _normalize_string_list(frontmatter.get("tools"))
    tags = _normalize_string_list(frontmatter.get("tags"))
    skills = _normalize_string_list(frontmatter.get("skills"))
    model = frontmatter.get("model")
    manager = frontmatter.get("manager")
    budget = frontmatter.get("budget") or {}
    memory = _normalize_memory_policy(frontmatter.get("memory_policy", frontmatter.get("memory")))
    permissions = _normalize_permissions(frontmatter.get("permissions"))
    output_schema = _normalize_output_schema(frontmatter.get("output_schema"))
    task_filters = _normalize_task_filters(frontmatter.get("task_filters"))
    fallback_model = str(frontmatter.get("fallback_model", "")).strip() or None
    escalation_path = str(frontmatter.get("escalation_path", "")).strip() or None
    parent_template_slug = str(frontmatter.get("parent_template", "")).strip() or None

    if not name:
        errors.append("`name` is required in frontmatter.")
    if not slug:
        errors.append("Agent slug could not be derived.")
    if not re.fullmatch(r"^[a-z0-9][a-z0-9\-]*$", slug):
        errors.append("`slug` must match `^[a-z0-9][a-z0-9-]*$`.")
    if version < 1:
        errors.append("`version` must be >= 1.")
    if not isinstance(budget, dict):
        errors.append("`budget` must be an object.")
    if not isinstance(memory, dict):
        errors.append("`memory_policy` must resolve to an object.")
    if not isinstance(permissions, (dict, str)):
        errors.append("`permissions` must be a string or an object.")
    if not isinstance(output_schema, dict):
        errors.append("`output_schema` must be an object.")

    if isinstance(budget, dict):
        for budget_key in ("token_budget", "time_budget_seconds", "retry_budget"):
            if budget_key in budget and not isinstance(budget[budget_key], (int, float)):
                errors.append(f"`budget.{budget_key}` must be a number.")

    valid_permission_values = {"read-only", "comment-only", "code-write", "merge-blocked"}
    if isinstance(permissions, dict):
        for perm_role, perm_value in permissions.items():
            if isinstance(perm_value, str) and perm_value not in valid_permission_values:
                errors.append(f"Unrecognised permission value '{perm_value}' for role '{perm_role}'.")
    elif isinstance(permissions, str) and permissions not in valid_permission_values:
        errors.append("`permissions` must be one of: read-only, comment-only, code-write, merge-blocked.")

    memory_scope = memory.get("scope")
    if memory_scope and memory_scope not in {"none", "project-only", "long-term"}:
        errors.append("`memory_policy.scope` must be one of: none, project-only, long-term.")

    output_format = output_schema.get("format")
    if output_format and output_format not in {"checklist", "json", "patch_proposal", "issue_reply", "adr"}:
        errors.append("`output_schema` must be one of: checklist, json, patch_proposal, issue_reply, adr.")

    for task_filter in task_filters:
        if _looks_like_regex(task_filter):
            try:
                re.compile(task_filter)
            except re.error as exc:
                errors.append(f"Invalid task filter regex '{task_filter}': {exc}")

    sections = _extract_sections(body)
    mission = sections.get("Mission", "").strip()
    rules_markdown = sections.get("Rules", "").strip()
    output_contract = sections.get("Output Contract", "").strip()
    description = str(frontmatter.get("description", "")).strip() or mission[:240] or None

    if not mission:
        errors.append("A `# Mission` section is required.")
    if not rules_markdown:
        errors.append("A `# Rules` section is required.")
    if not output_contract:
        errors.append("A `# Output Contract` section is required.")

    if errors:
        return None, errors

    normalized = {
        "name": name,
        "slug": slug,
        "description": description,
        "role": role,
        "version": version,
        "system_prompt": "\n\n".join(
            chunk for chunk in [mission, rules_markdown, output_contract] if chunk
        ),
        "mission_markdown": mission,
        "rules_markdown": rules_markdown,
        "output_contract_markdown": output_contract,
        "source_markdown": content,
        "capabilities": capabilities,
        "allowed_tools": tools,
        "task_filters": task_filters,
        "skills": skills,
        "parent_template_slug": parent_template_slug,
        "model_policy": {
            "model": model,
            "fallback_model": fallback_model,
            "escalation_path": escalation_path,
            "manager_slug": manager,
            "permissions": permissions,
        },
        "tags": tags,
        "budget": budget,
        "memory_policy": memory,
        "output_schema": output_schema,
    }
    return normalized, []


def _normalize_string_list(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _normalize_memory_policy(value: Any) -> dict[str, Any]:
    if value in (None, ""):
        return {}
    if isinstance(value, str):
        return {"scope": value.strip()}
    if isinstance(value, dict):
        return dict(value)
    return {}


def _normalize_permissions(value: Any) -> dict[str, Any] | str:
    if value in (None, ""):
        return {}
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        return {str(key): value_ for key, value_ in value.items()}
    return {}


def _normalize_output_schema(value: Any) -> dict[str, Any]:
    if value in (None, ""):
        return {}
    if isinstance(value, str):
        return {"format": value.strip()}
    if isinstance(value, dict):
        return dict(value)
    return {}


def _normalize_task_filters(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        normalized: list[str] = []
        for item in value:
            if isinstance(item, dict):
                text = str(item.get("pattern") or item.get("tag") or "").strip()
            else:
                text = str(item).strip()
            if text:
                normalized.append(text)
        return normalized
    return []


def _looks_like_regex(value: str) -> bool:
    return any(char in value for char in "^$[]().*+?{}\\|")


def _slugify(value: str) -> str:
    lowered = value.lower().strip()
    lowered = re.sub(r"[^a-z0-9]+", "-", lowered)
    return lowered.strip("-")


def _extract_sections(body: str) -> dict[str, str]:
    matches = list(HEADER_PATTERN.finditer(body))
    if not matches:
        return {}

    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        title = match.group(1).strip()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        sections[title] = body[start:end].strip()
    return sections
