"""Layer 5 — procedural snippets for prompts (Phase 5).

Full agent profiles carry large markdown fields; this module selects **bounded** excerpts
for the user context packet by task type / labels so the hot path does not always embed
entire mission + rules + contracts.
"""

from __future__ import annotations

from typing import Any


def build_procedural_snippets(
    agent: Any,
    task: Any,
    *,
    project_playbooks_excerpt: str = "",
    max_chars: int = 2400,
) -> str:
    """Return a markdown block of procedural excerpts (not a replacement for system prompt)."""
    if agent is None:
        return ""
    task_type = (task.task_type or "").lower() if task else ""
    labels = [x.lower() for x in (task.labels_json or [])] if task else []

    # Heuristic: code-heavy tasks get more output-contract; vague tasks get more rules.
    codeish = task_type in ("github_issue", "bug", "feature", "refactor") or any(
        "bug" in x or "api" in x for x in labels
    )

    mission_cap = 900 if codeish else 1200
    rules_cap = 700 if codeish else 1000
    contract_cap = 900 if codeish else 500

    parts: list[str] = []
    mission = (agent.mission_markdown or "").strip()
    if mission:
        miss_ex = mission[:mission_cap] + _ellipsis(mission, mission_cap)
        parts.append(f"### Mission (excerpt)\n{miss_ex}")
    rules = (agent.rules_markdown or "").strip()
    if rules:
        parts.append(f"### Rules (excerpt)\n{rules[:rules_cap]}{_ellipsis(rules, rules_cap)}")
    contract = (agent.output_contract_markdown or "").strip()
    if contract:
        cex = contract[:contract_cap] + _ellipsis(contract, contract_cap)
        parts.append(f"### Output contract (excerpt)\n{cex}")

    combined = "\n\n".join(parts).strip()
    extra = (project_playbooks_excerpt or "").strip()
    if extra:
        combined = (combined + "\n\n### Project playbooks (excerpt)\n" + extra).strip()
    if len(combined) > max_chars:
        combined = combined[: max_chars - 1] + "…"
    return combined


def _ellipsis(text: str, cap: int) -> str:
    return "…" if len(text) > cap else ""
