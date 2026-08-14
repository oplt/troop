# External effect and idempotency inventory (REL-001A)

Authoritative machine-readable source: `backend/modules/orchestration/external_effect_inventory.py`.

This document inventories every **mutating** native, GitHub, Gmail, Telegram, MCP, and A2A connector action. Read-only tools are listed briefly for completeness. Transport-level timeouts live in [EXTERNAL_CALL_INVENTORY.md](./EXTERNAL_CALL_INVENTORY.md).

## Enforcement

Actions **without durable idempotency** are **BLOCKED from new autonomous use**. `ToolRegistryService.authorize_tool()` upgrades an `autonomous` policy decision to `approval_required` when:

- the action contract marks `blocks_autonomous_use=True`, and
- no consumed approval is present in context.

Approval-gated execution remains allowed; REL-001B adds replay regression tests.

## Idempotency strategy legend

| Strategy | Meaning |
| --- | --- |
| `durable_claim` | Troop claims a unique DB idempotency key **before** calling the provider |
| `approval_dedup_only` | Dedupes approval record creation only; provider effect not receipted |
| `approval_payload_guard` | Soft guard in approval payload (e.g. `posted_comment_id`) |
| `none` | No Troop-side duplicate protection |

Only `durable_claim` permits autonomous mutating use.

---

## Gmail

| Action | Risk | Side effect | Approval | Idempotency | Ownership | Retry | Autonomous |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `gmail.search_messages` | low | read | autonomous | none (GET) | ConnectorInstallation.owner_id | safe GET retry | allowed |
| `gmail.get_message` | low | read | autonomous | none | installation owner | safe GET retry | allowed |
| `gmail.get_thread` | low | read | autonomous | none | installation owner | safe GET retry | allowed |
| `gmail.create_draft` | medium | external write | autonomous (catalog) | **none** | installation owner | replay → duplicate drafts | **BLOCKED** |
| `gmail.update_draft` | medium | external write | autonomous | **none** | installation + DraftExecutionMetadata | ambiguous replay | **BLOCKED** |
| `gmail.send_draft` | high | external write | approval_required + consumed approval | **durable_claim** (`ExternalActionExecution.idempotency_key` UNIQUE) | owner + approval hash + thread fingerprint | IntegrityError blocks concurrent send; succeeded row replays result | allowed only via approval path |
| `gmail.add_label` | medium | external write | autonomous | **none** | installation owner | single POST attempt | **BLOCKED** |

Reference implementation: `backend/modules/workforce/integrations/gmail.py:send_draft_exactly_once`.

---

## Telegram

| Action | Risk | Side effect | Approval | Idempotency | Ownership | Retry | Autonomous |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `telegram.send_message` | medium | external write | autonomous (catalog) | **none** | installation owner + bot token | Celery at-least-once → duplicate messages | **BLOCKED** |
| `telegram.edit_message` | medium | external write | autonomous | **none** | installation owner | no durable claim | **BLOCKED** |
| `telegram.answer_callback` | low | external write | autonomous | **none** (provider may reject duplicate callback_id) | installation owner | provider error on duplicate | **BLOCKED** |

---

## GitHub

Two execution surfaces share contracts:

1. **Orchestration toolbox** (`github_comment`, `github_label_issue`, `github_create_pr`) — agent/HITL path
2. **REST approval API** (`create_github_comment_approval`) — human approval + post

| Action | Risk | Side effect | Approval | Idempotency | Ownership | Retry | Autonomous |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `github_comment` | medium | external write | requires_approval / HITL dangerous_tool_call | approval_dedup (`github_outbound_dedup`) + payload guard (`posted_comment_id`) | SEC-001 `resolve_authorized_repository` + issue link | toolbox: no retry; API: skip if already posted | **BLOCKED** |
| `github_label_issue` | medium | external write | requires_approval / HITL | **none** | SEC-001 resolver | single POST | **BLOCKED** |
| `github_create_pr` | high | external write | requires_approval / HITL | **none** | SEC-001 resolver | single POST | **BLOCKED** |

---

## Native workspace tools

| Action | Risk | Side effect | Approval | Idempotency | Ownership | Retry | Autonomous |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `fs_write` | high | internal write | requires_approval / HITL | **none** | project-scoped path | overwrite on replay | **BLOCKED** |
| `code_execute` | high | internal write | requires_approval / HITL | **none** | project/run scoped sandbox | manual re-run | **BLOCKED** |
| `db_query` | critical | **read** (SELECT-only today) | requires_approval (catalog) | none | project_id filter | safe read retry | allowed (read) |
| `web_fetch` | low | read | autonomous | none (GET-only) | outbound URL allowlist | safe GET retry | allowed |
| `web_search` | low | read | autonomous | none | deployment API key | provider-dependent | allowed |
| `knowledge_search` | low | read | autonomous | none | project documents | safe read retry | allowed |
| `repo_search` | low | read | autonomous | none | linked repos | safe read retry | allowed |
| `fs_read` | low | read | autonomous | none | project-scoped path | safe read retry | allowed |

---

## MCP / A2A (dynamic)

| Pattern | Risk | Side effect | Approval | Idempotency | Ownership | Retry | Autonomous |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `mcp.*` | high | external write (assumed) | approval_required default | **none** | ConnectorInstallation.owner_id | workflow/Celery replay | **BLOCKED** |
| `a2a.*` | high | external write | approval_required (`a2a.send_task`) | **none** | A2A installation owner | failed status; replay duplicates | **BLOCKED** |

CONN-001 will add per-action manifest idempotency fields.

---

## Platform (non-tool) external writes

| Action | Risk | Side effect | Approval | Idempotency | Notes |
| --- | --- | --- | --- | --- | --- |
| `platform.smtp_send_email` | high | external write | system-only | **none** | `workers/email.py`; Celery at-least-once; REL-001B scope |

---

## Summary: autonomous BLOCKED mutators

These actions require approval (or future durable idempotency) before execution under an autonomous policy:

- `gmail.create_draft`, `gmail.update_draft`, `gmail.add_label`
- `telegram.send_message`, `telegram.edit_message`, `telegram.answer_callback`
- `github_comment`, `github_label_issue`, `github_create_pr`
- `fs_write`, `code_execute`
- All `mcp.*` and `a2a.*` tools

**Only mutator with durable idempotency today:** `gmail.send_draft` (already approval-gated).

---

## Related work

- REL-001B: `backend/tests/test_external_effect_replay.py` — duplicate webhook, Celery process skip, Gmail send replay, GitHub approval dedup, Telegram callback replay
- POL-001A: migrate this inventory into ToolDefinition/ActionPolicy metadata
- HITL-001B: commit-time authorization + provider receipts for GitHub
