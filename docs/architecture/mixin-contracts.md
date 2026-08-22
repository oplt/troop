# Service mixin contracts

This document freezes the implicit contracts of the remaining compatibility
mixins while domains migrate to explicit composition. A new mixin must declare
its required host attributes and sibling calls in its class docstring.

| Domain façade | Required host dependencies | Temporary sibling calls |
| --- | --- | --- |
| AI documents | `db`, `AiRepository`, provider registry | ingestion helpers |
| AI retrieval | `AiRepository`, provider registry | none |
| AI runs | `db`, `AiRepository`, provider registry | retrieval |
| AI reviews | `db`, `AiRepository` | none |
| AI evaluations | `db`, `AiRepository` | isolated run service per worker |
| Orchestration execution | `db`, orchestration/audit repositories, provider registry | projects, tasks, approvals, memory |
| Projects | `db`, orchestration/audit repositories | tasks, provider routing, memory |
| Tasks | `db`, orchestration/audit repositories | execution, GitHub, memory |
| Memory | `db`, orchestration/audit repositories, provider registry | project/task authorization, AI ingestion |

Prompt management is the first migrated slice: `AiService.prompts` is an
explicit `PromptService(db, repo)`. The old flat prompt methods remain a
compatibility bridge during call-site migration.

## Contract rules

1. A mixin may only use dependencies listed in its docstring or this table.
2. A domain service receives repositories/services explicitly in `__init__`.
3. Worker concurrency creates one database session per unit of work.
4. Router schemas and `UploadFile` stay at the HTTP adapter boundary in new code.
5. Compatibility façades delegate; they must not acquire new business logic.

