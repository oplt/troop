# API and UI parity inventory

This generated inventory classifies every FastAPI operation and records its intentional UI exposure. Regenerate it with `python scripts/api_ui_parity.py --write`.

Total operations: **533**. api-only: 2, deprecated: 23, internal: 34, ui-advanced: 48, ui-required: 426.

| Method | Endpoint | Classification | UI route | Surface | Frontend implementation |
| --- | --- | --- | --- | --- | --- |
| GET | `/api/v1/admin/audit-logs` | ui-required | `/admin/settings` | administration | frontend/src/api/admin.ts |
| GET | `/api/v1/admin/audit-logs/export` | ui-required | `/admin/settings` | administration | frontend/src/api/admin.ts |
| GET | `/api/v1/admin/identity-providers` | ui-required | `/admin/settings` | administration | frontend/src/api/admin.ts |
| POST | `/api/v1/admin/identity-providers` | ui-required | `/admin/settings` | administration | frontend/src/api/admin.ts |
| PATCH | `/api/v1/admin/identity-providers/{provider_id}` | ui-required | `/admin/settings` | administration | frontend/src/api/admin.ts |
| POST | `/api/v1/admin/identity-providers/{provider_id}/test` | ui-required | `/admin/settings` | administration | frontend/src/api/admin.ts |
| GET | `/api/v1/admin/metrics` | ui-advanced | n/a | administration | Intentional backend surface |
| GET | `/api/v1/admin/security-posture` | ui-required | `/admin/settings` | administration | frontend/src/api/admin.ts |
| GET | `/api/v1/admin/security-posture/export` | ui-required | `/admin/settings` | administration | frontend/src/api/admin.ts |
| GET | `/api/v1/admin/users` | ui-required | `/admin/settings` | administration | frontend/src/api/admin.ts |
| GET | `/api/v1/admin/users/{user_id}` | ui-advanced | n/a | administration | Intentional backend surface |
| PATCH | `/api/v1/admin/users/{user_id}/status` | ui-required | `/admin/settings` | administration | frontend/src/api/admin.ts |
| GET | `/api/v1/agents` | deprecated | n/a | compatibility | Intentional backend surface |
| POST | `/api/v1/agents` | deprecated | n/a | compatibility | Intentional backend surface |
| POST | `/api/v1/agents/import-markdown` | deprecated | n/a | compatibility | Intentional backend surface |
| DELETE | `/api/v1/agents/{agent_id}` | deprecated | n/a | compatibility | Intentional backend surface |
| GET | `/api/v1/agents/{agent_id}` | deprecated | n/a | compatibility | Intentional backend surface |
| PUT | `/api/v1/agents/{agent_id}` | deprecated | n/a | compatibility | Intentional backend surface |
| GET | `/api/v1/ai/documents` | ui-required | `/ai` | ai-studio | frontend/src/api/aiDocuments.ts |
| POST | `/api/v1/ai/documents` | ui-required | `/ai` | ai-studio | frontend/src/api/aiDocuments.ts |
| POST | `/api/v1/ai/documents/upload` | ui-required | `/ai` | ai-studio | frontend/src/api/aiDocuments.ts |
| GET | `/api/v1/ai/documents/{document_id}` | ui-required | `/ai` | ai-studio | frontend/src/api/aiDocuments.ts |
| GET | `/api/v1/ai/evaluation-datasets` | ui-required | `/ai` | ai-studio | frontend/src/api/aiEvaluations.ts |
| POST | `/api/v1/ai/evaluation-datasets` | ui-required | `/ai` | ai-studio | frontend/src/api/aiEvaluations.ts |
| PATCH | `/api/v1/ai/evaluation-datasets/{dataset_id}` | ui-required | `/ai` | ai-studio | frontend/src/api/aiEvaluations.ts |
| GET | `/api/v1/ai/evaluation-datasets/{dataset_id}/cases` | ui-required | `/ai` | ai-studio | frontend/src/api/aiEvaluations.ts |
| POST | `/api/v1/ai/evaluation-datasets/{dataset_id}/cases` | ui-required | `/ai` | ai-studio | frontend/src/api/aiEvaluations.ts |
| POST | `/api/v1/ai/evaluation-datasets/{dataset_id}/cases/from-trace` | ui-required | `/ai` | ai-studio | frontend/src/api/aiEvaluations.ts |
| POST | `/api/v1/ai/evaluation-datasets/{dataset_id}/run` | ui-required | `/ai` | ai-studio | frontend/src/api/aiEvaluations.ts |
| GET | `/api/v1/ai/evaluation-runs` | ui-required | `/ai` | ai-studio | frontend/src/api/aiEvaluations.ts |
| GET | `/api/v1/ai/evaluation-runs/{evaluation_run_id}` | ui-required | `/ai` | ai-studio | frontend/src/api/aiEvaluations.ts |
| GET | `/api/v1/ai/evaluation-runs/{evaluation_run_id}/scorecard` | ui-required | `/ai` | ai-studio | frontend/src/api/aiEvaluations.ts |
| GET | `/api/v1/ai/overview` | ui-required | `/ai` | ai-studio | frontend/src/api/aiPrompts.ts |
| GET | `/api/v1/ai/prompts` | ui-required | `/ai` | ai-studio | frontend/src/api/aiPrompts.ts |
| POST | `/api/v1/ai/prompts` | ui-required | `/ai` | ai-studio | frontend/src/api/aiPrompts.ts |
| PATCH | `/api/v1/ai/prompts/{template_id}` | ui-required | `/ai` | ai-studio | frontend/src/api/aiPrompts.ts |
| GET | `/api/v1/ai/prompts/{template_id}/versions` | ui-required | `/ai` | ai-studio | frontend/src/api/aiPrompts.ts |
| POST | `/api/v1/ai/prompts/{template_id}/versions` | ui-required | `/ai` | ai-studio | frontend/src/api/aiPrompts.ts |
| PATCH | `/api/v1/ai/prompts/{template_id}/versions/{version_id}` | ui-required | `/ai` | ai-studio | frontend/src/api/aiPrompts.ts |
| GET | `/api/v1/ai/providers` | ui-advanced | n/a | ai-studio | Intentional backend surface |
| POST | `/api/v1/ai/retrieve` | ui-required | `/ai` | ai-studio | frontend/src/api/aiDocuments.ts |
| GET | `/api/v1/ai/reviews` | ui-required | `/ai` | ai-studio | frontend/src/api/aiRuns.ts |
| POST | `/api/v1/ai/reviews/{review_id}/decision` | ui-required | `/ai` | ai-studio | frontend/src/api/aiRuns.ts |
| GET | `/api/v1/ai/runs` | ui-required | `/ai` | ai-studio | frontend/src/api/aiRuns.ts |
| POST | `/api/v1/ai/runs` | ui-required | `/ai` | ai-studio | frontend/src/api/aiRuns.ts |
| GET | `/api/v1/ai/runs/{run_id}` | ui-required | `/ai` | ai-studio | frontend/src/api/aiRuns.ts |
| GET | `/api/v1/ai/runs/{run_id}/feedback` | ui-required | `/ai` | ai-studio | frontend/src/api/aiRuns.ts |
| POST | `/api/v1/ai/runs/{run_id}/feedback` | ui-required | `/ai` | ai-studio | frontend/src/api/aiRuns.ts |
| POST | `/api/v1/ai/runs/{run_id}/reviews` | ui-required | `/ai` | ai-studio | frontend/src/api/aiRuns.ts |
| POST | `/api/v1/auth/forgot-password` | ui-required | `/` | authentication | frontend/src/api/auth.ts |
| POST | `/api/v1/auth/logout` | ui-required | `/` | authentication | frontend/src/api/auth.ts |
| GET | `/api/v1/auth/me` | ui-required | `/` | authentication | frontend/src/api/auth.ts |
| POST | `/api/v1/auth/mfa/disable` | ui-required | `/` | authentication | frontend/src/api/auth.ts |
| POST | `/api/v1/auth/mfa/enable` | ui-required | `/` | authentication | frontend/src/api/auth.ts |
| POST | `/api/v1/auth/mfa/verify` | ui-required | `/` | authentication | frontend/src/api/auth.ts |
| POST | `/api/v1/auth/refresh` | ui-required | `/` | authentication | frontend/src/api/auth.ts<br>frontend/src/api/client.ts |
| POST | `/api/v1/auth/resend-verification` | ui-required | `/` | authentication | frontend/src/api/auth.ts |
| POST | `/api/v1/auth/reset-password` | ui-required | `/` | authentication | frontend/src/api/auth.ts |
| POST | `/api/v1/auth/sign-in` | ui-required | `/` | authentication | frontend/src/api/auth.ts |
| POST | `/api/v1/auth/sign-up` | ui-required | `/` | authentication | frontend/src/api/auth.ts |
| GET | `/api/v1/auth/sso/callback` | internal | n/a | authentication | Intentional backend surface |
| GET | `/api/v1/auth/sso/providers` | ui-required | `/` | authentication | frontend/src/api/auth.ts |
| GET | `/api/v1/auth/sso/{provider_slug}/authorize` | ui-advanced | n/a | authentication | Intentional backend surface |
| POST | `/api/v1/auth/verify-email` | ui-required | `/` | authentication | frontend/src/api/auth.ts |
| GET | `/api/v1/auth/workspaces` | ui-advanced | n/a | authentication | Intentional backend surface |
| GET | `/api/v1/calendar/items` | ui-required | `/calendar` | calendar | frontend/src/api/calendar.ts |
| POST | `/api/v1/calendar/items` | ui-required | `/calendar` | calendar | frontend/src/api/calendar.ts |
| DELETE | `/api/v1/calendar/items/{entry_id}` | ui-required | `/calendar` | calendar | frontend/src/api/calendar.ts |
| GET | `/api/v1/calendar/items/{entry_id}` | ui-required | `/calendar` | calendar | frontend/src/api/calendar.ts |
| PATCH | `/api/v1/calendar/items/{entry_id}` | ui-required | `/calendar` | calendar | frontend/src/api/calendar.ts |
| GET | `/api/v1/companies` | ui-required | `/companies` | organization | frontend/src/api/companies.ts |
| POST | `/api/v1/companies` | ui-required | `/companies` | organization | frontend/src/api/companies.ts |
| GET | `/api/v1/companies/default` | ui-required | `/companies` | organization | frontend/src/api/companies.ts |
| PATCH | `/api/v1/companies/{company_id}` | ui-required | `/companies` | organization | frontend/src/api/companies.ts |
| GET | `/api/v1/graphql` | ui-required | `/hierarchy` | hierarchy | frontend/src/api/orchestrationGraphql.ts |
| POST | `/api/v1/graphql` | ui-required | `/hierarchy` | hierarchy | frontend/src/api/orchestrationGraphql.ts |
| GET | `/api/v1/memory` | deprecated | n/a | compatibility | Intentional backend surface |
| POST | `/api/v1/memory` | deprecated | n/a | compatibility | Intentional backend surface |
| POST | `/api/v1/memory/search` | deprecated | n/a | compatibility | Intentional backend surface |
| DELETE | `/api/v1/memory/{memory_id}` | deprecated | n/a | compatibility | Intentional backend surface |
| PATCH | `/api/v1/memory/{memory_id}` | deprecated | n/a | compatibility | Intentional backend surface |
| GET | `/api/v1/notifications` | ui-required | `/notifications` | notifications | frontend/src/api/notifications.ts |
| GET | `/api/v1/notifications/preferences` | ui-required | `/notifications` | notifications | frontend/src/api/notifications.ts |
| PUT | `/api/v1/notifications/preferences` | ui-required | `/notifications` | notifications | frontend/src/api/notifications.ts |
| PATCH | `/api/v1/notifications/read-all` | ui-required | `/notifications` | notifications | frontend/src/api/notifications.ts |
| GET | `/api/v1/notifications/unread-count` | ui-required | `/notifications` | notifications | frontend/src/api/notifications.ts |
| PATCH | `/api/v1/notifications/{notification_id}/read` | ui-required | `/notifications` | notifications | frontend/src/api/notifications.ts |
| GET | `/api/v1/orchestration/activation` | ui-required | `/dashboard` | operations | frontend/src/api/orchestration/analytics.ts |
| GET | `/api/v1/orchestration/agent-patterns` | ui-required | `/dashboard` | operations | frontend/src/api/orchestration/analytics.ts |
| GET | `/api/v1/orchestration/agents` | ui-required | `/agents` | agents | frontend/src/api/orchestration/agents.ts |
| POST | `/api/v1/orchestration/agents` | ui-required | `/agents` | agents | frontend/src/api/orchestration/agents.ts |
| POST | `/api/v1/orchestration/agents/from-template/{template_slug}` | ui-required | `/agents` | agents | frontend/src/api/orchestration/agents.ts |
| POST | `/api/v1/orchestration/agents/import` | ui-required | `/agents` | agents | frontend/src/api/orchestration/agents.ts |
| GET | `/api/v1/orchestration/agents/skills` | ui-required | `/agents` | agents | frontend/src/api/orchestration/agents.ts |
| POST | `/api/v1/orchestration/agents/skills` | ui-required | `/agents` | agents | frontend/src/api/orchestration/agents.ts |
| DELETE | `/api/v1/orchestration/agents/skills/{slug}` | ui-required | `/agents` | agents | frontend/src/api/orchestration/agents.ts |
| PATCH | `/api/v1/orchestration/agents/skills/{slug}` | ui-required | `/agents` | agents | frontend/src/api/orchestration/agents.ts |
| GET | `/api/v1/orchestration/agents/templates` | ui-required | `/agents` | agents | frontend/src/api/orchestration/agents.ts |
| POST | `/api/v1/orchestration/agents/templates` | ui-required | `/agents` | agents | frontend/src/api/orchestration/agents.ts |
| DELETE | `/api/v1/orchestration/agents/templates/slug/{slug}` | ui-required | `/agents` | agents | frontend/src/api/orchestration/agents.ts |
| PATCH | `/api/v1/orchestration/agents/templates/slug/{slug}` | ui-required | `/agents` | agents | frontend/src/api/orchestration/agents.ts |
| DELETE | `/api/v1/orchestration/agents/templates/{template_id}` | ui-required | `/agents` | agents | frontend/src/api/orchestration/agents.ts |
| PATCH | `/api/v1/orchestration/agents/templates/{template_id}` | ui-required | `/agents` | agents | frontend/src/api/orchestration/agents.ts |
| POST | `/api/v1/orchestration/agents/validate-contract` | ui-required | `/agents` | agents | frontend/src/api/orchestration/agents.ts |
| POST | `/api/v1/orchestration/agents/validate-markdown` | ui-required | `/agents` | agents | frontend/src/api/orchestration/agents.ts |
| DELETE | `/api/v1/orchestration/agents/{agent_id}` | ui-required | `/agents` | agents | frontend/src/api/orchestration/agents.ts |
| GET | `/api/v1/orchestration/agents/{agent_id}` | ui-required | `/agents` | agents | frontend/src/api/orchestration/agents.ts |
| PATCH | `/api/v1/orchestration/agents/{agent_id}` | ui-required | `/agents` | agents | frontend/src/api/orchestration/agents.ts |
| POST | `/api/v1/orchestration/agents/{agent_id}/activate` | ui-required | `/agents` | agents | frontend/src/api/orchestration/agents.ts |
| POST | `/api/v1/orchestration/agents/{agent_id}/deactivate` | ui-required | `/agents` | agents | frontend/src/api/orchestration/agents.ts |
| POST | `/api/v1/orchestration/agents/{agent_id}/duplicate` | ui-required | `/agents` | agents | frontend/src/api/orchestration/agents.ts |
| POST | `/api/v1/orchestration/agents/{agent_id}/simulate` | ui-required | `/agents` | agents | frontend/src/api/orchestration/agents.ts |
| POST | `/api/v1/orchestration/agents/{agent_id}/skills/pins` | ui-advanced | n/a | agents | Intentional backend surface |
| POST | `/api/v1/orchestration/agents/{agent_id}/test-run` | ui-required | `/agents` | agents | frontend/src/api/orchestration/agents.ts |
| GET | `/api/v1/orchestration/agents/{agent_id}/versions` | ui-required | `/agents` | agents | frontend/src/api/orchestration/agents.ts |
| GET | `/api/v1/orchestration/analytics/agent-performance` | ui-required | `/analytics/execution` | observability | frontend/src/api/orchestration/analytics.ts |
| GET | `/api/v1/orchestration/analytics/budget-projection` | ui-required | `/analytics/execution` | observability | frontend/src/api/orchestration/analytics.ts |
| GET | `/api/v1/orchestration/analytics/cost` | ui-required | `/analytics/cost` | cost | frontend/src/api/orchestration/analytics.ts |
| GET | `/api/v1/orchestration/analytics/execution-insights` | ui-required | `/analytics/execution` | observability | frontend/src/api/orchestration/analytics.ts |
| GET | `/api/v1/orchestration/approvals` | ui-required | `/approvals` | approvals | frontend/src/api/orchestration/approvals.ts |
| GET | `/api/v1/orchestration/approvals/pending-count` | ui-required | `/approvals` | approvals | frontend/src/api/orchestration/approvals.ts |
| GET | `/api/v1/orchestration/approvals/{approval_id}` | ui-required | `/approvals` | approvals | frontend/src/api/orchestration/approvals.ts |
| POST | `/api/v1/orchestration/approvals/{approval_id}` | ui-required | `/approvals` | approvals | frontend/src/api/orchestration/approvals.ts |
| POST | `/api/v1/orchestration/approvals/{approval_id}/delegate` | ui-advanced | n/a | approvals | Intentional backend surface |
| PATCH | `/api/v1/orchestration/approvals/{approval_id}/payload` | ui-required | `/approvals` | approvals | frontend/src/api/integrations.ts |
| POST | `/api/v1/orchestration/approvals/{approval_id}/request-changes` | ui-required | `/approvals` | approvals | frontend/src/api/integrations.ts |
| GET | `/api/v1/orchestration/brainstorms` | ui-required | `/brainstorms` | brainstorms | frontend/src/api/orchestration/projects.ts |
| POST | `/api/v1/orchestration/brainstorms` | ui-required | `/brainstorms` | brainstorms | frontend/src/api/orchestration/projects.ts |
| GET | `/api/v1/orchestration/brainstorms/{brainstorm_id}` | ui-required | `/brainstorms` | brainstorms | frontend/src/api/orchestration/projects.ts |
| GET | `/api/v1/orchestration/brainstorms/{brainstorm_id}/discourse-insights` | ui-required | `/brainstorms` | brainstorms | frontend/src/api/orchestration/analytics.ts |
| POST | `/api/v1/orchestration/brainstorms/{brainstorm_id}/export-artifact` | ui-required | `/brainstorms` | brainstorms | frontend/src/api/orchestration/projects.ts |
| POST | `/api/v1/orchestration/brainstorms/{brainstorm_id}/force-summary` | ui-required | `/brainstorms` | brainstorms | frontend/src/api/orchestration/projects.ts |
| GET | `/api/v1/orchestration/brainstorms/{brainstorm_id}/messages` | ui-required | `/brainstorms` | brainstorms | frontend/src/api/orchestration/projects.ts |
| POST | `/api/v1/orchestration/brainstorms/{brainstorm_id}/next-round` | ui-required | `/brainstorms` | brainstorms | frontend/src/api/orchestration/projects.ts |
| GET | `/api/v1/orchestration/brainstorms/{brainstorm_id}/participants` | ui-required | `/brainstorms` | brainstorms | frontend/src/api/orchestration/projects.ts |
| POST | `/api/v1/orchestration/brainstorms/{brainstorm_id}/participants` | ui-required | `/brainstorms` | brainstorms | frontend/src/api/orchestration/projects.ts |
| DELETE | `/api/v1/orchestration/brainstorms/{brainstorm_id}/participants/{participant_id}` | ui-required | `/brainstorms` | brainstorms | frontend/src/api/orchestration/projects.ts |
| PATCH | `/api/v1/orchestration/brainstorms/{brainstorm_id}/participants/{participant_id}` | ui-required | `/brainstorms` | brainstorms | frontend/src/api/orchestration/projects.ts |
| POST | `/api/v1/orchestration/brainstorms/{brainstorm_id}/promote` | ui-required | `/brainstorms` | brainstorms | frontend/src/api/orchestration/projects.ts |
| POST | `/api/v1/orchestration/brainstorms/{brainstorm_id}/promote-adr` | ui-required | `/brainstorms` | brainstorms | frontend/src/api/orchestration/projects.ts |
| POST | `/api/v1/orchestration/brainstorms/{brainstorm_id}/promote-document` | ui-required | `/brainstorms` | brainstorms | frontend/src/api/orchestration/projects.ts |
| POST | `/api/v1/orchestration/brainstorms/{brainstorm_id}/start` | ui-required | `/brainstorms` | brainstorms | frontend/src/api/orchestration/projects.ts |
| GET | `/api/v1/orchestration/companies/{company_id}/semantic-memory` | ui-required | `/dashboard` | operations | frontend/src/api/orchestration/memory.ts |
| POST | `/api/v1/orchestration/durable-engine/recovery-benchmark` | api-only | n/a | operations | Intentional backend surface |
| GET | `/api/v1/orchestration/durable-engine/review` | ui-advanced | n/a | operations | Intentional backend surface |
| GET | `/api/v1/orchestration/github/app/callback` | internal | n/a | integrations | Intentional backend surface |
| GET | `/api/v1/orchestration/github/app/install-url` | ui-required | `/admin/settings` | integrations | frontend/src/api/orchestration/projects.ts |
| GET | `/api/v1/orchestration/github/connections` | ui-required | `/admin/settings` | integrations | frontend/src/api/orchestration/projects.ts |
| POST | `/api/v1/orchestration/github/connections` | ui-required | `/admin/settings` | integrations | frontend/src/api/orchestration/projects.ts |
| DELETE | `/api/v1/orchestration/github/connections/{connection_id}` | ui-required | `/admin/settings` | integrations | frontend/src/api/orchestration/projects.ts |
| POST | `/api/v1/orchestration/github/connections/{connection_id}/sync-repos` | ui-required | `/admin/settings` | integrations | frontend/src/api/orchestration/projects.ts |
| POST | `/api/v1/orchestration/github/import-issues` | ui-required | `/admin/settings` | integrations | frontend/src/api/orchestration/projects.ts |
| GET | `/api/v1/orchestration/github/issues` | ui-required | `/admin/settings` | integrations | frontend/src/api/orchestration/projects.ts |
| POST | `/api/v1/orchestration/github/issues/{issue_link_id}/comment` | ui-required | `/admin/settings` | integrations | frontend/src/api/orchestration/projects.ts |
| POST | `/api/v1/orchestration/github/issues/{issue_link_id}/pr` | ui-required | `/admin/settings` | integrations | frontend/src/api/orchestration/projects.ts |
| POST | `/api/v1/orchestration/github/issues/{issue_link_id}/refresh` | ui-required | `/admin/settings` | integrations | frontend/src/api/orchestration/projects.ts |
| GET | `/api/v1/orchestration/github/repositories` | ui-required | `/admin/settings` | integrations | frontend/src/api/orchestration/projects.ts |
| GET | `/api/v1/orchestration/github/sync-events` | ui-advanced | n/a | integrations | Intentional backend surface |
| GET | `/api/v1/orchestration/github/sync-events/stream` | internal | n/a | integrations | Intentional backend surface |
| POST | `/api/v1/orchestration/github/sync-events/{sync_event_id}/replay` | ui-required | `/admin/settings` | integrations | frontend/src/api/orchestration/projects.ts |
| GET | `/api/v1/orchestration/hierarchy/stream` | internal | n/a | operations | Intentional backend surface |
| GET | `/api/v1/orchestration/hitl/audit-logs` | ui-required | `/activity` | audit | frontend/src/api/orchestration/approvals.ts |
| POST | `/api/v1/orchestration/local-repo/validate` | ui-required | `/dashboard` | operations | frontend/src/api/orchestration/projects.ts |
| GET | `/api/v1/orchestration/memory-metrics` | ui-required | `/dashboard` | operations | frontend/src/api/orchestration/memory.ts |
| GET | `/api/v1/orchestration/overview` | ui-required | `/dashboard` | operations | frontend/src/api/orchestration/analytics.ts |
| GET | `/api/v1/orchestration/portfolio` | ui-required | `/portfolio` | portfolio | frontend/src/api/orchestration/analytics.ts |
| GET | `/api/v1/orchestration/portfolio/control-plane` | ui-required | `/portfolio` | portfolio | frontend/src/api/orchestration/analytics.ts |
| GET | `/api/v1/orchestration/portfolio/execution-policy` | ui-required | `/portfolio` | portfolio | frontend/src/api/orchestration/analytics.ts |
| PUT | `/api/v1/orchestration/portfolio/execution-policy` | ui-required | `/portfolio` | portfolio | frontend/src/api/orchestration/analytics.ts |
| GET | `/api/v1/orchestration/portfolio/stream` | internal | n/a | portfolio | Intentional backend surface |
| POST | `/api/v1/orchestration/pr-assistant/review` | ui-advanced | n/a | operations | Intentional backend surface |
| GET | `/api/v1/orchestration/projects` | ui-required | `/projects/:projectId` | project | frontend/src/api/orchestration/projects.ts |
| POST | `/api/v1/orchestration/projects` | ui-required | `/projects/:projectId` | project | frontend/src/api/orchestration/projects.ts |
| POST | `/api/v1/orchestration/projects/bootstrap-apply` | ui-required | `/projects/:projectId` | project | frontend/src/api/orchestration/projects.ts |
| POST | `/api/v1/orchestration/projects/bootstrap-from-text` | ui-required | `/projects/:projectId` | project | frontend/src/api/orchestration/projects.ts |
| DELETE | `/api/v1/orchestration/projects/{project_id}` | ui-required | `/projects/:projectId` | project | frontend/src/api/orchestration/projects.ts |
| GET | `/api/v1/orchestration/projects/{project_id}` | ui-required | `/projects/:projectId` | project | frontend/src/api/orchestration/projects.ts |
| PATCH | `/api/v1/orchestration/projects/{project_id}` | ui-required | `/projects/:projectId` | project | frontend/src/api/orchestration/projects.ts |
| GET | `/api/v1/orchestration/projects/{project_id}/agent-patterns` | ui-required | `/projects/:projectId` | project | frontend/src/api/orchestration/analytics.ts |
| POST | `/api/v1/orchestration/projects/{project_id}/agent-patterns/evals/{eval_id}/score` | ui-required | `/projects/:projectId` | project | frontend/src/api/orchestration/analytics.ts |
| POST | `/api/v1/orchestration/projects/{project_id}/agent-patterns/{pattern_id}/apply` | ui-required | `/projects/:projectId` | project | frontend/src/api/orchestration/analytics.ts |
| POST | `/api/v1/orchestration/projects/{project_id}/agent-patterns/{pattern_id}/benchmark` | ui-required | `/projects/:projectId` | project | frontend/src/api/orchestration/analytics.ts |
| POST | `/api/v1/orchestration/projects/{project_id}/agent-patterns/{pattern_id}/enable` | ui-required | `/projects/:projectId` | project | frontend/src/api/orchestration/analytics.ts |
| GET | `/api/v1/orchestration/projects/{project_id}/agents` | ui-required | `/projects/:projectId` | project | frontend/src/api/orchestration/projects.ts |
| POST | `/api/v1/orchestration/projects/{project_id}/agents` | ui-required | `/projects/:projectId` | project | frontend/src/api/orchestration/projects.ts |
| DELETE | `/api/v1/orchestration/projects/{project_id}/agents/{membership_id}` | ui-required | `/projects/:projectId` | project | frontend/src/api/orchestration/projects.ts |
| PATCH | `/api/v1/orchestration/projects/{project_id}/agents/{membership_id}` | ui-required | `/projects/:projectId` | project | frontend/src/api/orchestration/projects.ts |
| GET | `/api/v1/orchestration/projects/{project_id}/dag/ready-tasks` | ui-required | `/projects/:projectId` | project | frontend/src/api/orchestration/projects.ts |
| POST | `/api/v1/orchestration/projects/{project_id}/dag/start-ready` | ui-required | `/projects/:projectId` | project | frontend/src/api/orchestration/projects.ts |
| GET | `/api/v1/orchestration/projects/{project_id}/decisions` | ui-required | `/projects/:projectId` | project | frontend/src/api/orchestration/projects.ts |
| POST | `/api/v1/orchestration/projects/{project_id}/decisions` | ui-required | `/projects/:projectId` | project | frontend/src/api/orchestration/projects.ts |
| GET | `/api/v1/orchestration/projects/{project_id}/documents` | ui-required | `/projects/:projectId` | project | frontend/src/api/orchestration/projects.ts |
| POST | `/api/v1/orchestration/projects/{project_id}/documents` | ui-required | `/projects/:projectId` | project | frontend/src/api/orchestration/projects.ts |
| DELETE | `/api/v1/orchestration/projects/{project_id}/documents/{document_id}` | ui-required | `/projects/:projectId` | project | frontend/src/api/orchestration/projects.ts |
| GET | `/api/v1/orchestration/projects/{project_id}/episodic-memory/archives` | ui-required | `/projects/:projectId` | project | frontend/src/api/orchestration/memory.ts |
| GET | `/api/v1/orchestration/projects/{project_id}/episodic-memory/archives/{archive_id}/download` | ui-advanced | n/a | project | Intentional backend surface |
| POST | `/api/v1/orchestration/projects/{project_id}/episodic-memory/reindex` | ui-required | `/projects/:projectId` | project | frontend/src/api/orchestration/memory.ts |
| GET | `/api/v1/orchestration/projects/{project_id}/episodic-memory/search` | ui-required | `/projects/:projectId` | project | frontend/src/api/orchestration/memory.ts |
| GET | `/api/v1/orchestration/projects/{project_id}/evals` | ui-required | `/projects/:projectId/benchmark` | evaluation | frontend/src/api/orchestration/analytics.ts |
| POST | `/api/v1/orchestration/projects/{project_id}/evals` | ui-required | `/projects/:projectId/benchmark` | evaluation | frontend/src/api/orchestration/analytics.ts |
| POST | `/api/v1/orchestration/projects/{project_id}/evals/benchmark-historical` | ui-required | `/projects/:projectId/benchmark` | evaluation | frontend/src/api/orchestration/analytics.ts |
| POST | `/api/v1/orchestration/projects/{project_id}/evals/cross-project-dependencies` | ui-required | `/projects/:projectId/benchmark` | evaluation | frontend/src/api/orchestration/analytics.ts |
| GET | `/api/v1/orchestration/projects/{project_id}/evals/leaderboard` | ui-required | `/projects/:projectId/benchmark` | evaluation | frontend/src/api/orchestration/analytics.ts |
| PATCH | `/api/v1/orchestration/projects/{project_id}/evals/{eval_id}` | ui-required | `/projects/:projectId/benchmark` | evaluation | frontend/src/api/orchestration/analytics.ts |
| POST | `/api/v1/orchestration/projects/{project_id}/evals/{eval_id}/score` | ui-required | `/projects/:projectId/benchmark` | evaluation | frontend/src/api/orchestration/analytics.ts |
| POST | `/api/v1/orchestration/projects/{project_id}/evals/{eval_id}/start` | ui-required | `/projects/:projectId/benchmark` | evaluation | frontend/src/api/orchestration/analytics.ts |
| GET | `/api/v1/orchestration/projects/{project_id}/gate-config` | ui-required | `/projects/:projectId` | project | frontend/src/api/orchestration/projects.ts |
| PATCH | `/api/v1/orchestration/projects/{project_id}/gate-config` | ui-required | `/projects/:projectId` | project | frontend/src/api/orchestration/projects.ts |
| GET | `/api/v1/orchestration/projects/{project_id}/hierarchy-policy` | ui-required | `/projects/:projectId` | project | frontend/src/api/orchestration/projects.ts |
| PUT | `/api/v1/orchestration/projects/{project_id}/hierarchy-policy` | ui-required | `/projects/:projectId` | project | frontend/src/api/orchestration/projects.ts |
| GET | `/api/v1/orchestration/projects/{project_id}/knowledge` | ui-required | `/projects/:projectId` | project | frontend/src/api/orchestration/memory.ts |
| GET | `/api/v1/orchestration/projects/{project_id}/knowledge-graph/edges` | ui-required | `/projects/:projectId` | project | frontend/src/api/orchestration/memory.ts |
| POST | `/api/v1/orchestration/projects/{project_id}/knowledge-graph/edges` | ui-required | `/projects/:projectId` | project | frontend/src/api/orchestration/memory.ts |
| DELETE | `/api/v1/orchestration/projects/{project_id}/knowledge-graph/edges/{edge_id}` | ui-required | `/projects/:projectId` | project | frontend/src/api/orchestration/memory.ts |
| GET | `/api/v1/orchestration/projects/{project_id}/live-snapshot` | ui-required | `/projects/:projectId` | project | frontend/src/api/orchestration/projects.ts |
| GET | `/api/v1/orchestration/projects/{project_id}/local-repo` | ui-required | `/projects/:projectId` | project | frontend/src/api/orchestration/projects.ts |
| PUT | `/api/v1/orchestration/projects/{project_id}/local-repo` | ui-required | `/projects/:projectId` | project | frontend/src/api/orchestration/projects.ts |
| POST | `/api/v1/orchestration/projects/{project_id}/local-repo/commands` | ui-required | `/projects/:projectId` | project | frontend/src/api/orchestration/projects.ts |
| GET | `/api/v1/orchestration/projects/{project_id}/local-repo/files` | ui-required | `/projects/:projectId` | project | frontend/src/api/orchestration/projects.ts |
| GET | `/api/v1/orchestration/projects/{project_id}/memory` | ui-required | `/projects/:projectId` | project | frontend/src/api/orchestration/memory.ts |
| POST | `/api/v1/orchestration/projects/{project_id}/memory` | ui-required | `/projects/:projectId` | project | frontend/src/api/orchestration/memory.ts |
| GET | `/api/v1/orchestration/projects/{project_id}/memory-ingest-jobs` | ui-required | `/projects/:projectId` | project | frontend/src/api/orchestration/memory.ts |
| GET | `/api/v1/orchestration/projects/{project_id}/memory-settings` | ui-required | `/projects/:projectId` | project | frontend/src/api/orchestration/memory.ts |
| PATCH | `/api/v1/orchestration/projects/{project_id}/memory-settings` | ui-required | `/projects/:projectId` | project | frontend/src/api/orchestration/memory.ts |
| DELETE | `/api/v1/orchestration/projects/{project_id}/memory/{memory_id}` | ui-required | `/projects/:projectId` | project | frontend/src/api/orchestration/memory.ts |
| GET | `/api/v1/orchestration/projects/{project_id}/milestones` | ui-required | `/projects/:projectId` | project | frontend/src/api/orchestration/projects.ts |
| POST | `/api/v1/orchestration/projects/{project_id}/milestones` | ui-required | `/projects/:projectId` | project | frontend/src/api/orchestration/projects.ts |
| PATCH | `/api/v1/orchestration/projects/{project_id}/milestones/{milestone_id}` | ui-required | `/projects/:projectId` | project | frontend/src/api/orchestration/projects.ts |
| GET | `/api/v1/orchestration/projects/{project_id}/procedural-playbooks` | ui-required | `/projects/:projectId` | project | frontend/src/api/orchestration/memory.ts |
| POST | `/api/v1/orchestration/projects/{project_id}/procedural-playbooks` | ui-required | `/projects/:projectId` | project | frontend/src/api/orchestration/memory.ts |
| DELETE | `/api/v1/orchestration/projects/{project_id}/procedural-playbooks/{playbook_id}` | ui-advanced | n/a | project | Intentional backend surface |
| PATCH | `/api/v1/orchestration/projects/{project_id}/procedural-playbooks/{playbook_id}` | ui-advanced | n/a | project | Intentional backend surface |
| GET | `/api/v1/orchestration/projects/{project_id}/repositories` | ui-required | `/projects/:projectId` | project | frontend/src/api/orchestration/projects.ts |
| POST | `/api/v1/orchestration/projects/{project_id}/repositories` | ui-required | `/projects/:projectId` | project | frontend/src/api/orchestration/projects.ts |
| GET | `/api/v1/orchestration/projects/{project_id}/repositories/index-status` | ui-required | `/projects/:projectId` | project | frontend/src/api/orchestration/projects.ts |
| PATCH | `/api/v1/orchestration/projects/{project_id}/repositories/{repository_link_id}` | ui-required | `/projects/:projectId` | project | frontend/src/api/orchestration/projects.ts |
| POST | `/api/v1/orchestration/projects/{project_id}/repositories/{repository_link_id}/index` | ui-required | `/projects/:projectId` | project | frontend/src/api/orchestration/projects.ts |
| GET | `/api/v1/orchestration/projects/{project_id}/schedules` | ui-advanced | n/a | project | Intentional backend surface |
| POST | `/api/v1/orchestration/projects/{project_id}/schedules` | ui-advanced | n/a | project | Intentional backend surface |
| GET | `/api/v1/orchestration/projects/{project_id}/semantic-memory` | ui-required | `/projects/:projectId` | knowledge | frontend/src/api/orchestration/memory.ts |
| POST | `/api/v1/orchestration/projects/{project_id}/semantic-memory` | ui-required | `/projects/:projectId` | knowledge | frontend/src/api/orchestration/memory.ts |
| GET | `/api/v1/orchestration/projects/{project_id}/semantic-memory/conflicts` | ui-required | `/projects/:projectId` | knowledge | frontend/src/api/orchestration/memory.ts |
| POST | `/api/v1/orchestration/projects/{project_id}/semantic-memory/links` | ui-required | `/projects/:projectId` | knowledge | frontend/src/api/orchestration/memory.ts |
| DELETE | `/api/v1/orchestration/projects/{project_id}/semantic-memory/links/{link_id}` | ui-advanced | n/a | knowledge | Intentional backend surface |
| POST | `/api/v1/orchestration/projects/{project_id}/semantic-memory/merge` | ui-required | `/projects/:projectId` | knowledge | frontend/src/api/orchestration/memory.ts |
| POST | `/api/v1/orchestration/projects/{project_id}/semantic-memory/promote-from-working-memory` | ui-required | `/projects/:projectId` | knowledge | frontend/src/api/orchestration/memory.ts |
| DELETE | `/api/v1/orchestration/projects/{project_id}/semantic-memory/{entry_id}` | ui-required | `/projects/:projectId` | knowledge | frontend/src/api/orchestration/memory.ts |
| GET | `/api/v1/orchestration/projects/{project_id}/semantic-memory/{entry_id}` | ui-required | `/projects/:projectId` | knowledge | frontend/src/api/orchestration/memory.ts |
| PATCH | `/api/v1/orchestration/projects/{project_id}/semantic-memory/{entry_id}` | ui-required | `/projects/:projectId` | knowledge | frontend/src/api/orchestration/memory.ts |
| GET | `/api/v1/orchestration/projects/{project_id}/semantic-memory/{entry_id}/links` | ui-advanced | n/a | knowledge | Intentional backend surface |
| GET | `/api/v1/orchestration/projects/{project_id}/stream` | internal | n/a | project | Intentional backend surface |
| GET | `/api/v1/orchestration/projects/{project_id}/tasks` | ui-required | `/projects/:projectId` | project | frontend/src/api/orchestration/projects.ts |
| POST | `/api/v1/orchestration/projects/{project_id}/tasks` | ui-required | `/projects/:projectId` | project | frontend/src/api/orchestration/projects.ts |
| DELETE | `/api/v1/orchestration/projects/{project_id}/tasks/{task_id}` | ui-required | `/projects/:projectId` | project | frontend/src/api/orchestration/projects.ts |
| GET | `/api/v1/orchestration/projects/{project_id}/tasks/{task_id}` | ui-required | `/projects/:projectId` | project | frontend/src/api/orchestration/projects.ts |
| PATCH | `/api/v1/orchestration/projects/{project_id}/tasks/{task_id}` | ui-required | `/projects/:projectId` | project | frontend/src/api/orchestration/projects.ts |
| PATCH | `/api/v1/orchestration/projects/{project_id}/tasks/{task_id}/agent-session` | ui-required | `/projects/:projectId` | project | frontend/src/api/orchestration/projects.ts |
| POST | `/api/v1/orchestration/projects/{project_id}/tasks/{task_id}/agent-session` | ui-required | `/projects/:projectId` | project | frontend/src/api/orchestration/projects.ts |
| POST | `/api/v1/orchestration/projects/{project_id}/tasks/{task_id}/agent-session/context-pack` | ui-required | `/projects/:projectId` | project | frontend/src/api/orchestration/projects.ts |
| POST | `/api/v1/orchestration/projects/{project_id}/tasks/{task_id}/agent-session/quality-score` | ui-required | `/projects/:projectId` | project | frontend/src/api/orchestration/projects.ts |
| POST | `/api/v1/orchestration/projects/{project_id}/tasks/{task_id}/agent-session/worktree` | ui-required | `/projects/:projectId` | project | frontend/src/api/orchestration/projects.ts |
| GET | `/api/v1/orchestration/projects/{project_id}/tasks/{task_id}/artifacts` | ui-required | `/projects/:projectId` | project | frontend/src/api/orchestration/projects.ts |
| POST | `/api/v1/orchestration/projects/{project_id}/tasks/{task_id}/artifacts` | ui-required | `/projects/:projectId` | project | frontend/src/api/orchestration/projects.ts |
| POST | `/api/v1/orchestration/projects/{project_id}/tasks/{task_id}/assign` | ui-required | `/projects/:projectId` | project | frontend/src/api/orchestration/projects.ts |
| GET | `/api/v1/orchestration/projects/{project_id}/tasks/{task_id}/blockers` | ui-required | `/projects/:projectId` | project | frontend/src/api/orchestration/projects.ts |
| POST | `/api/v1/orchestration/projects/{project_id}/tasks/{task_id}/check-acceptance` | ui-required | `/projects/:projectId` | project | frontend/src/api/orchestration/projects.ts |
| GET | `/api/v1/orchestration/projects/{project_id}/tasks/{task_id}/comments` | ui-advanced | n/a | project | Intentional backend surface |
| POST | `/api/v1/orchestration/projects/{project_id}/tasks/{task_id}/comments` | ui-advanced | n/a | project | Intentional backend surface |
| POST | `/api/v1/orchestration/projects/{project_id}/tasks/{task_id}/decompose` | ui-required | `/projects/:projectId` | project | frontend/src/api/orchestration/projects.ts |
| GET | `/api/v1/orchestration/projects/{project_id}/tasks/{task_id}/execution-state` | ui-required | `/projects/:projectId` | project | frontend/src/api/orchestration/runs.ts |
| GET | `/api/v1/orchestration/projects/{project_id}/tasks/{task_id}/memory-coordination` | ui-required | `/projects/:projectId` | project | frontend/src/api/orchestration/memory.ts |
| PATCH | `/api/v1/orchestration/projects/{project_id}/tasks/{task_id}/memory-coordination` | ui-required | `/projects/:projectId` | project | frontend/src/api/orchestration/memory.ts |
| GET | `/api/v1/orchestration/projects/{project_id}/tasks/{task_id}/merge-preview` | ui-required | `/projects/:projectId` | project | frontend/src/api/orchestration/projects.ts |
| POST | `/api/v1/orchestration/projects/{project_id}/tasks/{task_id}/merge-resolve-run` | ui-required | `/projects/:projectId` | project | frontend/src/api/orchestration/projects.ts |
| POST | `/api/v1/orchestration/projects/{project_id}/tasks/{task_id}/runs` | ui-required | `/projects/:projectId` | project | frontend/src/api/orchestration/projects.ts |
| GET | `/api/v1/orchestration/projects/{project_id}/tasks/{task_id}/subtasks` | ui-required | `/projects/:projectId` | project | frontend/src/api/orchestration/projects.ts |
| GET | `/api/v1/orchestration/projects/{project_id}/tasks/{task_id}/timeline` | ui-required | `/projects/:projectId` | project | frontend/src/api/orchestration/analytics.ts |
| GET | `/api/v1/orchestration/projects/{project_id}/workflow-templates/custom` | ui-required | `/projects/:projectId` | project | frontend/src/api/orchestration/templates.ts |
| POST | `/api/v1/orchestration/projects/{project_id}/workflow-templates/custom` | ui-required | `/projects/:projectId` | project | frontend/src/api/orchestration/templates.ts |
| POST | `/api/v1/orchestration/projects/{project_id}/workflow-templates/{template_id}/apply` | ui-required | `/projects/:projectId` | project | frontend/src/api/orchestration/templates.ts |
| GET | `/api/v1/orchestration/providers` | ui-required | `/dashboard` | operations | frontend/src/api/orchestration/providers.ts |
| POST | `/api/v1/orchestration/providers` | ui-required | `/dashboard` | operations | frontend/src/api/orchestration/providers.ts |
| POST | `/api/v1/orchestration/providers/compare` | ui-required | `/dashboard` | operations | frontend/src/api/orchestration/providers.ts |
| POST | `/api/v1/orchestration/providers/health-check` | ui-required | `/dashboard` | operations | frontend/src/api/orchestration/providers.ts |
| GET | `/api/v1/orchestration/providers/health-summary` | ui-required | `/dashboard` | operations | frontend/src/api/orchestration/providers.ts |
| GET | `/api/v1/orchestration/providers/model-capabilities` | ui-required | `/dashboard` | operations | frontend/src/api/orchestration/providers.ts |
| DELETE | `/api/v1/orchestration/providers/{provider_id}` | ui-required | `/dashboard` | operations | frontend/src/api/orchestration/providers.ts |
| PATCH | `/api/v1/orchestration/providers/{provider_id}` | ui-required | `/dashboard` | operations | frontend/src/api/orchestration/providers.ts |
| GET | `/api/v1/orchestration/providers/{provider_id}/models` | ui-required | `/dashboard` | operations | frontend/src/api/orchestration/providers.ts |
| POST | `/api/v1/orchestration/providers/{provider_id}/runtime/start` | ui-required | `/dashboard` | operations | frontend/src/api/orchestration/providers.ts |
| POST | `/api/v1/orchestration/providers/{provider_id}/test` | ui-required | `/dashboard` | operations | frontend/src/api/orchestration/providers.ts |
| GET | `/api/v1/orchestration/runs` | ui-required | `/runs/:runId` | runs | frontend/src/api/orchestration/runs.ts |
| GET | `/api/v1/orchestration/runs/{run_id}` | ui-required | `/runs/:runId` | runs | frontend/src/api/orchestration/runs.ts |
| POST | `/api/v1/orchestration/runs/{run_id}/cancel` | ui-required | `/runs/:runId` | runs | frontend/src/api/orchestration/runs.ts |
| GET | `/api/v1/orchestration/runs/{run_id}/cost` | ui-required | `/runs/:runId` | runs | frontend/src/api/orchestration/runs.ts |
| GET | `/api/v1/orchestration/runs/{run_id}/durable-workflow` | ui-required | `/runs/:runId` | runs | frontend/src/api/orchestration/runs.ts |
| GET | `/api/v1/orchestration/runs/{run_id}/events` | ui-required | `/runs/:runId` | runs | frontend/src/api/orchestration/runs.ts |
| GET | `/api/v1/orchestration/runs/{run_id}/execution-state` | ui-required | `/runs/:runId` | runs | frontend/src/api/orchestration/runs.ts |
| GET | `/api/v1/orchestration/runs/{run_id}/explanation` | ui-required | `/runs/:runId` | runs | frontend/src/api/orchestration/runs.ts |
| POST | `/api/v1/orchestration/runs/{run_id}/replay` | ui-required | `/runs/:runId` | runs | frontend/src/api/orchestration/runs.ts |
| POST | `/api/v1/orchestration/runs/{run_id}/resume` | ui-required | `/runs/:runId` | runs | frontend/src/api/orchestration/runs.ts |
| POST | `/api/v1/orchestration/runs/{run_id}/retry` | ui-required | `/runs/:runId` | runs | frontend/src/api/orchestration/runs.ts |
| POST | `/api/v1/orchestration/runs/{run_id}/signals` | ui-required | `/runs/:runId` | runs | frontend/src/api/orchestration/runs.ts |
| GET | `/api/v1/orchestration/runs/{run_id}/stream` | internal | n/a | runs | Intentional backend surface |
| GET | `/api/v1/orchestration/runs/{run_id}/trace` | ui-required | `/runs/:runId` | runs | frontend/src/api/orchestration/runs.ts |
| GET | `/api/v1/orchestration/runs/{run_id}/working-memory` | ui-required | `/runs/:runId` | runs | frontend/src/api/orchestration/runs.ts |
| PATCH | `/api/v1/orchestration/runs/{run_id}/working-memory` | ui-required | `/runs/:runId` | runs | frontend/src/api/orchestration/runs.ts |
| GET | `/api/v1/orchestration/runtime-info` | ui-required | `/dashboard` | operations | frontend/src/api/orchestration/analytics.ts |
| GET | `/api/v1/orchestration/skills/marketplace` | ui-advanced | n/a | operations | Intentional backend surface |
| GET | `/api/v1/orchestration/tasks/my` | ui-required | `/runs/:runId` | runs | frontend/src/api/orchestration/projects.ts |
| GET | `/api/v1/orchestration/teams/profiles` | ui-required | `/hierarchy` | hierarchy | frontend/src/api/orchestration/agents.ts |
| POST | `/api/v1/orchestration/teams/profiles/from-template` | ui-required | `/hierarchy` | hierarchy | frontend/src/api/orchestration/agents.ts |
| GET | `/api/v1/orchestration/teams/templates` | ui-required | `/hierarchy` | hierarchy | frontend/src/api/orchestration/agents.ts |
| POST | `/api/v1/orchestration/teams/templates` | ui-required | `/hierarchy` | hierarchy | frontend/src/api/orchestration/agents.ts |
| DELETE | `/api/v1/orchestration/teams/templates/{template_id}` | ui-required | `/hierarchy` | hierarchy | frontend/src/api/orchestration/agents.ts |
| PATCH | `/api/v1/orchestration/teams/templates/{template_id}` | ui-required | `/hierarchy` | hierarchy | frontend/src/api/orchestration/agents.ts |
| GET | `/api/v1/orchestration/workflow-templates` | ui-required | `/dashboard` | operations | frontend/src/api/orchestration/templates.ts |
| GET | `/api/v1/orchestration/workspace/stream` | internal | n/a | operations | Intentional backend surface |
| GET | `/api/v1/platform/admin/config` | ui-required | `/admin/settings` | platform-admin | frontend/src/api/platform.ts |
| PUT | `/api/v1/platform/admin/config` | ui-required | `/admin/settings` | platform-admin | frontend/src/api/platform.ts |
| GET | `/api/v1/platform/admin/email-templates` | ui-required | `/admin/settings` | platform-admin | frontend/src/api/platform.ts |
| POST | `/api/v1/platform/admin/email-templates` | ui-required | `/admin/settings` | platform-admin | frontend/src/api/platform.ts |
| PATCH | `/api/v1/platform/admin/email-templates/{template_id}` | ui-required | `/admin/settings` | platform-admin | frontend/src/api/platform.ts |
| GET | `/api/v1/platform/admin/feature-flags` | ui-required | `/admin/settings` | platform-admin | frontend/src/api/platform.ts |
| POST | `/api/v1/platform/admin/feature-flags` | ui-required | `/admin/settings` | platform-admin | frontend/src/api/platform.ts |
| PATCH | `/api/v1/platform/admin/feature-flags/{feature_flag_id}` | ui-required | `/admin/settings` | platform-admin | frontend/src/api/platform.ts |
| GET | `/api/v1/platform/admin/plans` | ui-required | `/admin/settings` | platform-admin | frontend/src/api/platform.ts |
| POST | `/api/v1/platform/admin/plans` | ui-required | `/admin/settings` | platform-admin | frontend/src/api/platform.ts |
| PATCH | `/api/v1/platform/admin/plans/{plan_id}` | ui-required | `/admin/settings` | platform-admin | frontend/src/api/platform.ts |
| GET | `/api/v1/platform/api-keys` | ui-required | `/admin/settings` | platform-admin | frontend/src/api/platform.ts |
| POST | `/api/v1/platform/api-keys` | ui-required | `/admin/settings` | platform-admin | frontend/src/api/platform.ts |
| DELETE | `/api/v1/platform/api-keys/{api_key_id}` | ui-required | `/admin/settings` | platform-admin | frontend/src/api/platform.ts |
| GET | `/api/v1/platform/billing/plans` | ui-required | `/admin/settings` | platform-admin | frontend/src/api/platform.ts |
| GET | `/api/v1/platform/billing/subscription` | ui-required | `/admin/settings` | platform-admin | frontend/src/api/platform.ts |
| PUT | `/api/v1/platform/billing/subscription` | ui-required | `/admin/settings` | platform-admin | frontend/src/api/platform.ts |
| GET | `/api/v1/platform/feature-flags` | ui-required | `/admin/settings` | platform-admin | frontend/src/api/platform.ts |
| GET | `/api/v1/platform/metadata` | ui-required | `/admin/settings` | platform-admin | frontend/src/api/platform.ts |
| GET | `/api/v1/platform/webhooks` | ui-required | `/admin/settings` | platform-admin | frontend/src/api/platform.ts |
| POST | `/api/v1/platform/webhooks` | ui-required | `/admin/settings` | platform-admin | frontend/src/api/platform.ts |
| DELETE | `/api/v1/platform/webhooks/{webhook_id}` | ui-required | `/admin/settings` | platform-admin | frontend/src/api/platform.ts |
| PATCH | `/api/v1/platform/webhooks/{webhook_id}` | ui-required | `/admin/settings` | platform-admin | frontend/src/api/platform.ts |
| POST | `/api/v1/platform/webhooks/{webhook_id}/test` | ui-required | `/admin/settings` | platform-admin | frontend/src/api/platform.ts |
| GET | `/api/v1/profile` | ui-required | `/profile` | profile | frontend/src/api/profile.ts |
| PUT | `/api/v1/profile` | ui-required | `/profile` | profile | frontend/src/api/profile.ts |
| DELETE | `/api/v1/profile/avatar` | ui-required | `/profile` | profile | frontend/src/api/profile.ts |
| POST | `/api/v1/profile/avatar` | ui-required | `/profile` | profile | frontend/src/api/profile.ts |
| POST | `/api/v1/rag/projects/{project_id}/answer` | ui-advanced | n/a | knowledge | Intentional backend surface |
| POST | `/api/v1/rag/projects/{project_id}/answer/stream` | internal | n/a | knowledge | Intentional backend surface |
| GET | `/api/v1/rag/projects/{project_id}/documents` | ui-advanced | n/a | knowledge | Intentional backend surface |
| POST | `/api/v1/rag/projects/{project_id}/documents` | ui-advanced | n/a | knowledge | Intentional backend surface |
| POST | `/api/v1/rag/projects/{project_id}/documents/bulk` | ui-advanced | n/a | knowledge | Intentional backend surface |
| POST | `/api/v1/rag/projects/{project_id}/documents/upload` | ui-advanced | n/a | knowledge | Intentional backend surface |
| DELETE | `/api/v1/rag/projects/{project_id}/documents/{document_id}` | ui-advanced | n/a | knowledge | Intentional backend surface |
| GET | `/api/v1/rag/projects/{project_id}/documents/{document_id}` | ui-advanced | n/a | knowledge | Intentional backend surface |
| POST | `/api/v1/rag/projects/{project_id}/documents/{document_id}/reindex` | ui-advanced | n/a | knowledge | Intentional backend surface |
| POST | `/api/v1/rag/projects/{project_id}/search` | ui-advanced | n/a | knowledge | Intentional backend surface |
| GET | `/api/v1/runs/{run_id}` | deprecated | n/a | compatibility | frontend/src/api/orchestration/runs.ts |
| POST | `/api/v1/runs/{run_id}/approve-plan` | deprecated | n/a | compatibility | frontend/src/api/orchestration/runs.ts |
| GET | `/api/v1/runs/{run_id}/artifacts` | deprecated | n/a | compatibility | frontend/src/api/orchestration/runs.ts |
| POST | `/api/v1/runs/{run_id}/cancel` | deprecated | n/a | compatibility | frontend/src/api/orchestration/runs.ts |
| GET | `/api/v1/runs/{run_id}/steps` | deprecated | n/a | compatibility | frontend/src/api/orchestration/runs.ts |
| GET | `/api/v1/runs/{run_id}/workspace-files` | deprecated | n/a | compatibility | Intentional backend surface |
| GET | `/api/v1/settings/config` | ui-required | `/admin/settings` | settings | frontend/src/api/settings.ts |
| PUT | `/api/v1/settings/config` | ui-required | `/admin/settings` | settings | frontend/src/api/settings.ts |
| GET | `/api/v1/settings/database` | ui-required | `/admin/settings` | settings | frontend/src/api/settings.ts |
| POST | `/api/v1/settings/database` | ui-required | `/admin/settings` | settings | frontend/src/api/settings.ts |
| GET | `/api/v1/settings/database/catalog` | ui-required | `/admin/settings` | settings | frontend/src/api/settings.ts |
| DELETE | `/api/v1/settings/database/{setting_id}` | ui-required | `/admin/settings` | settings | frontend/src/api/settings.ts |
| PATCH | `/api/v1/settings/database/{setting_id}` | ui-required | `/admin/settings` | settings | frontend/src/api/settings.ts |
| GET | `/api/v1/tasks` | deprecated | n/a | compatibility | Intentional backend surface |
| POST | `/api/v1/tasks` | deprecated | n/a | compatibility | Intentional backend surface |
| GET | `/api/v1/tasks/{task_id}` | deprecated | n/a | compatibility | Intentional backend surface |
| POST | `/api/v1/tasks/{task_id}/runs` | deprecated | n/a | compatibility | frontend/src/api/orchestration/projects.ts |
| GET | `/api/v1/tools` | deprecated | n/a | compatibility | frontend/src/api/orchestration/agents.ts |
| GET | `/api/v1/tools/{name}` | deprecated | n/a | compatibility | Intentional backend surface |
| GET | `/api/v1/users/directory` | ui-required | `/profile` | profile | frontend/src/api/users.ts |
| GET | `/api/v1/users/me` | ui-required | `/profile` | profile | frontend/src/api/users.ts |
| PATCH | `/api/v1/users/me` | ui-required | `/profile` | profile | frontend/src/api/users.ts |
| PATCH | `/api/v1/users/me/password` | ui-required | `/profile` | profile | frontend/src/api/users.ts |
| GET | `/api/v1/users/me/sessions` | ui-required | `/profile` | profile | frontend/src/api/users.ts |
| DELETE | `/api/v1/users/me/sessions/{session_id}` | ui-required | `/profile` | profile | frontend/src/api/users.ts |
| GET | `/api/v1/workforce/connector-operations` | ui-required | `/my-tasks` | workforce | frontend/src/api/integrations.ts |
| GET | `/api/v1/workforce/connectors/definitions` | ui-required | `/integrations` | integrations | frontend/src/api/integrations.ts<br>frontend/src/api/workforce.ts |
| POST | `/api/v1/workforce/connectors/definitions/seed` | api-only | n/a | integrations | Intentional backend surface |
| POST | `/api/v1/workforce/connectors/gmail/authorize` | ui-required | `/integrations` | integrations | frontend/src/api/integrations.ts |
| GET | `/api/v1/workforce/connectors/gmail/callback` | internal | n/a | integrations | Intentional backend surface |
| GET | `/api/v1/workforce/connectors/gmail/status` | ui-required | `/integrations` | integrations | frontend/src/api/integrations.ts |
| POST | `/api/v1/workforce/connectors/gmail/{installation_id}/disconnect` | ui-required | `/integrations` | integrations | frontend/src/api/integrations.ts |
| POST | `/api/v1/workforce/connectors/google_calendar/authorize` | ui-required | `/integrations` | integrations | frontend/src/api/integrations.ts |
| GET | `/api/v1/workforce/connectors/google_calendar/callback` | internal | n/a | integrations | Intentional backend surface |
| GET | `/api/v1/workforce/connectors/google_calendar/status` | ui-required | `/integrations` | integrations | frontend/src/api/integrations.ts |
| POST | `/api/v1/workforce/connectors/google_calendar/{installation_id}/disconnect` | ui-required | `/integrations` | integrations | frontend/src/api/integrations.ts |
| POST | `/api/v1/workforce/connectors/google_drive/authorize` | ui-required | `/integrations` | integrations | frontend/src/api/integrations.ts |
| GET | `/api/v1/workforce/connectors/google_drive/callback` | internal | n/a | integrations | Intentional backend surface |
| GET | `/api/v1/workforce/connectors/google_drive/status` | ui-required | `/integrations` | integrations | frontend/src/api/integrations.ts |
| POST | `/api/v1/workforce/connectors/google_drive/{installation_id}/disconnect` | ui-required | `/integrations` | integrations | frontend/src/api/integrations.ts |
| POST | `/api/v1/workforce/connectors/hubspot/authorize` | ui-required | `/integrations` | integrations | frontend/src/api/integrations.ts |
| GET | `/api/v1/workforce/connectors/hubspot/callback` | internal | n/a | integrations | Intentional backend surface |
| GET | `/api/v1/workforce/connectors/hubspot/status` | ui-required | `/integrations` | integrations | frontend/src/api/integrations.ts |
| POST | `/api/v1/workforce/connectors/hubspot/{installation_id}/disconnect` | ui-required | `/integrations` | integrations | frontend/src/api/integrations.ts |
| GET | `/api/v1/workforce/connectors/installations` | ui-required | `/integrations` | integrations | frontend/src/api/integrations.ts<br>frontend/src/api/workforce.ts |
| POST | `/api/v1/workforce/connectors/installations` | ui-required | `/integrations` | integrations | frontend/src/api/integrations.ts<br>frontend/src/api/workforce.ts |
| PATCH | `/api/v1/workforce/connectors/installations/{installation_id}` | ui-advanced | n/a | integrations | Intentional backend surface |
| POST | `/api/v1/workforce/connectors/installations/{installation_id}/test` | ui-required | `/integrations` | integrations | frontend/src/api/integrations.ts<br>frontend/src/api/workforce.ts |
| POST | `/api/v1/workforce/connectors/jira/authorize` | ui-required | `/integrations` | integrations | frontend/src/api/integrations.ts |
| GET | `/api/v1/workforce/connectors/jira/callback` | internal | n/a | integrations | Intentional backend surface |
| GET | `/api/v1/workforce/connectors/jira/status` | ui-required | `/integrations` | integrations | frontend/src/api/integrations.ts |
| POST | `/api/v1/workforce/connectors/jira/{installation_id}/disconnect` | ui-required | `/integrations` | integrations | frontend/src/api/integrations.ts |
| POST | `/api/v1/workforce/connectors/linear/authorize` | ui-required | `/integrations` | integrations | frontend/src/api/integrations.ts |
| GET | `/api/v1/workforce/connectors/linear/callback` | internal | n/a | integrations | Intentional backend surface |
| GET | `/api/v1/workforce/connectors/linear/status` | ui-required | `/integrations` | integrations | frontend/src/api/integrations.ts |
| POST | `/api/v1/workforce/connectors/linear/{installation_id}/disconnect` | ui-required | `/integrations` | integrations | frontend/src/api/integrations.ts |
| GET | `/api/v1/workforce/connectors/manifests` | ui-required | `/integrations` | integrations | frontend/src/api/integrations.ts |
| GET | `/api/v1/workforce/connectors/manifests/{provider_slug}` | ui-required | `/integrations` | integrations | frontend/src/api/integrations.ts |
| POST | `/api/v1/workforce/connectors/microsoft_calendar/authorize` | ui-required | `/integrations` | integrations | frontend/src/api/integrations.ts |
| GET | `/api/v1/workforce/connectors/microsoft_calendar/callback` | internal | n/a | integrations | Intentional backend surface |
| GET | `/api/v1/workforce/connectors/microsoft_calendar/status` | ui-required | `/integrations` | integrations | frontend/src/api/integrations.ts |
| POST | `/api/v1/workforce/connectors/microsoft_calendar/{installation_id}/disconnect` | ui-required | `/integrations` | integrations | frontend/src/api/integrations.ts |
| POST | `/api/v1/workforce/connectors/microsoft_drive/authorize` | ui-required | `/integrations` | integrations | frontend/src/api/integrations.ts |
| GET | `/api/v1/workforce/connectors/microsoft_drive/callback` | internal | n/a | integrations | Intentional backend surface |
| GET | `/api/v1/workforce/connectors/microsoft_drive/status` | ui-required | `/integrations` | integrations | frontend/src/api/integrations.ts |
| POST | `/api/v1/workforce/connectors/microsoft_drive/{installation_id}/disconnect` | ui-required | `/integrations` | integrations | frontend/src/api/integrations.ts |
| POST | `/api/v1/workforce/connectors/outlook/authorize` | ui-required | `/integrations` | integrations | frontend/src/api/integrations.ts |
| GET | `/api/v1/workforce/connectors/outlook/callback` | internal | n/a | integrations | Intentional backend surface |
| GET | `/api/v1/workforce/connectors/outlook/status` | ui-required | `/integrations` | integrations | frontend/src/api/integrations.ts |
| POST | `/api/v1/workforce/connectors/outlook/{installation_id}/disconnect` | ui-required | `/integrations` | integrations | frontend/src/api/integrations.ts |
| POST | `/api/v1/workforce/connectors/salesforce/authorize` | ui-required | `/integrations` | integrations | frontend/src/api/integrations.ts |
| GET | `/api/v1/workforce/connectors/salesforce/callback` | internal | n/a | integrations | Intentional backend surface |
| GET | `/api/v1/workforce/connectors/salesforce/status` | ui-required | `/integrations` | integrations | frontend/src/api/integrations.ts |
| POST | `/api/v1/workforce/connectors/salesforce/{installation_id}/disconnect` | ui-required | `/integrations` | integrations | frontend/src/api/integrations.ts |
| POST | `/api/v1/workforce/connectors/slack/authorize` | ui-required | `/integrations` | integrations | frontend/src/api/integrations.ts |
| GET | `/api/v1/workforce/connectors/slack/bindings` | ui-advanced | n/a | integrations | Intentional backend surface |
| DELETE | `/api/v1/workforce/connectors/slack/bindings/{binding_id}` | ui-required | `/integrations` | integrations | frontend/src/api/integrations.ts |
| GET | `/api/v1/workforce/connectors/slack/callback` | internal | n/a | integrations | Intentional backend surface |
| POST | `/api/v1/workforce/connectors/slack/link` | ui-required | `/integrations` | integrations | frontend/src/api/integrations.ts |
| GET | `/api/v1/workforce/connectors/slack/status` | ui-required | `/integrations` | integrations | frontend/src/api/integrations.ts |
| POST | `/api/v1/workforce/connectors/teams/authorize` | ui-required | `/integrations` | integrations | frontend/src/api/integrations.ts |
| GET | `/api/v1/workforce/connectors/teams/bindings` | ui-advanced | n/a | integrations | Intentional backend surface |
| DELETE | `/api/v1/workforce/connectors/teams/bindings/{binding_id}` | ui-required | `/integrations` | integrations | frontend/src/api/integrations.ts |
| GET | `/api/v1/workforce/connectors/teams/callback` | internal | n/a | integrations | Intentional backend surface |
| POST | `/api/v1/workforce/connectors/teams/link` | ui-required | `/integrations` | integrations | frontend/src/api/integrations.ts |
| GET | `/api/v1/workforce/connectors/teams/status` | ui-required | `/integrations` | integrations | frontend/src/api/integrations.ts |
| GET | `/api/v1/workforce/connectors/telegram/bindings` | ui-advanced | n/a | integrations | Intentional backend surface |
| DELETE | `/api/v1/workforce/connectors/telegram/bindings/{binding_id}` | ui-required | `/integrations` | integrations | frontend/src/api/integrations.ts |
| POST | `/api/v1/workforce/connectors/telegram/link` | ui-required | `/integrations` | integrations | frontend/src/api/integrations.ts |
| GET | `/api/v1/workforce/connectors/telegram/status` | ui-required | `/integrations` | integrations | frontend/src/api/integrations.ts |
| POST | `/api/v1/workforce/connectors/telegram/{installation_id}/configure-webhook` | ui-required | `/integrations` | integrations | frontend/src/api/integrations.ts |
| GET | `/api/v1/workforce/departments` | ui-required | `/departments` | departments | frontend/src/api/workforce.ts |
| POST | `/api/v1/workforce/departments` | ui-required | `/departments` | departments | frontend/src/api/workforce.ts |
| PATCH | `/api/v1/workforce/departments/{department_id}` | ui-required | `/departments` | departments | frontend/src/api/workforce.ts |
| POST | `/api/v1/workforce/departments/{department_id}/archive` | ui-required | `/departments` | departments | frontend/src/api/workforce.ts |
| GET | `/api/v1/workforce/knowledge-sources` | ui-advanced | n/a | workforce | Intentional backend surface |
| POST | `/api/v1/workforce/knowledge-sources` | ui-advanced | n/a | workforce | Intentional backend surface |
| POST | `/api/v1/workforce/knowledge-sources/{source_id}/sync` | ui-advanced | n/a | workforce | Intentional backend surface |
| GET | `/api/v1/workforce/marketplace` | ui-required | `/marketplace` | marketplace | frontend/src/api/workforce.ts |
| GET | `/api/v1/workforce/marketplace/agent-templates` | ui-advanced | n/a | marketplace | Intentional backend surface |
| POST | `/api/v1/workforce/marketplace/agent-templates/install` | ui-required | `/marketplace` | marketplace | frontend/src/api/workforce.ts |
| POST | `/api/v1/workforce/marketplace/agent-templates/seed` | ui-required | `/marketplace` | marketplace | frontend/src/api/workforce.ts |
| GET | `/api/v1/workforce/marketplace/departments` | ui-advanced | n/a | marketplace | Intentional backend surface |
| POST | `/api/v1/workforce/marketplace/departments/install` | ui-required | `/marketplace` | marketplace | frontend/src/api/workforce.ts |
| GET | `/api/v1/workforce/marketplace/policy` | ui-advanced | n/a | marketplace | Intentional backend surface |
| GET | `/api/v1/workforce/marketplace/skills` | ui-advanced | n/a | marketplace | Intentional backend surface |
| POST | `/api/v1/workforce/marketplace/skills/install` | ui-required | `/marketplace` | marketplace | frontend/src/api/workforce.ts |
| GET | `/api/v1/workforce/marketplace/workflows` | ui-advanced | n/a | marketplace | Intentional backend surface |
| POST | `/api/v1/workforce/marketplace/workflows/email-approval/bootstrap` | ui-required | `/marketplace` | marketplace | frontend/src/api/workforce.ts |
| POST | `/api/v1/workforce/marketplace/workflows/install` | ui-required | `/marketplace` | marketplace | frontend/src/api/workforce.ts |
| GET | `/api/v1/workforce/marketplace/workspace-packages` | ui-required | `/marketplace` | marketplace | frontend/src/api/workforce.ts |
| POST | `/api/v1/workforce/marketplace/workspace-packages/import` | ui-required | `/marketplace` | marketplace | frontend/src/api/workforce.ts |
| GET | `/api/v1/workforce/marketplace/workspace-packages/{package_id}` | ui-advanced | n/a | marketplace | Intentional backend surface |
| POST | `/api/v1/workforce/marketplace/workspace-packages/{package_id}/install` | ui-required | `/marketplace` | marketplace | frontend/src/api/workforce.ts |
| GET | `/api/v1/workforce/marketplace/workspace-packages/{package_id}/permission-diff` | ui-required | `/marketplace` | marketplace | frontend/src/api/workforce.ts |
| POST | `/api/v1/workforce/marketplace/workspace-packages/{package_id}/publish-public` | ui-advanced | n/a | marketplace | Intentional backend surface |
| POST | `/api/v1/workforce/marketplace/workspace-packages/{package_id}/versions` | ui-advanced | n/a | marketplace | Intentional backend surface |
| POST | `/api/v1/workforce/projects/{project_id}/analyze` | ui-required | `/my-tasks` | workforce | frontend/src/api/workforce.ts |
| GET | `/api/v1/workforce/skill-drafts` | ui-required | `/my-tasks` | workforce | frontend/src/api/workforce.ts |
| POST | `/api/v1/workforce/skill-drafts` | ui-required | `/my-tasks` | workforce | frontend/src/api/workforce.ts |
| POST | `/api/v1/workforce/skill-drafts/import-markdown` | ui-required | `/my-tasks` | workforce | frontend/src/api/workforce.ts |
| GET | `/api/v1/workforce/skill-drafts/{draft_id}` | ui-required | `/my-tasks` | workforce | frontend/src/api/workforce.ts |
| PATCH | `/api/v1/workforce/skill-drafts/{draft_id}` | ui-required | `/my-tasks` | workforce | frontend/src/api/workforce.ts |
| POST | `/api/v1/workforce/skill-drafts/{draft_id}/publish` | ui-required | `/my-tasks` | workforce | frontend/src/api/workforce.ts |
| POST | `/api/v1/workforce/skill-drafts/{draft_id}/validate` | ui-required | `/my-tasks` | workforce | frontend/src/api/workforce.ts |
| GET | `/api/v1/workforce/skills` | ui-required | `/skills` | skills | frontend/src/api/workforce.ts |
| POST | `/api/v1/workforce/skills/migrate-skill-packs` | ui-required | `/skills` | skills | frontend/src/api/workforce.ts |
| POST | `/api/v1/workforce/skills/reconcile-uncertain-ownership` | ui-required | `/skills` | skills | frontend/src/api/workforce.ts |
| GET | `/api/v1/workforce/skills/{skill_id}` | ui-required | `/skills` | skills | frontend/src/api/workforce.ts |
| POST | `/api/v1/workforce/skills/{skill_id}/improve` | ui-advanced | n/a | skills | Intentional backend surface |
| POST | `/api/v1/workforce/skills/{skill_id}/promote` | ui-required | `/skills` | skills | frontend/src/api/workforce.ts |
| GET | `/api/v1/workforce/skills/{skill_id}/usage` | ui-required | `/skills` | skills | frontend/src/api/workforce.ts |
| GET | `/api/v1/workforce/skills/{skill_id}/versions` | ui-required | `/skills` | skills | frontend/src/api/workforce.ts |
| GET | `/api/v1/workforce/tasks/{task_id}/agent-matches` | ui-required | `/my-tasks` | workforce | frontend/src/api/workforce.ts |
| GET | `/api/v1/workforce/tasks/{task_id}/analysis` | ui-required | `/my-tasks` | workforce | frontend/src/api/workforce.ts |
| POST | `/api/v1/workforce/tasks/{task_id}/analyze` | ui-required | `/my-tasks` | workforce | frontend/src/api/workforce.ts |
| POST | `/api/v1/workforce/tasks/{task_id}/assemble-agent` | ui-required | `/my-tasks` | workforce | frontend/src/api/workforce.ts |
| POST | `/api/v1/workforce/tasks/{task_id}/generate-skills` | ui-required | `/my-tasks` | workforce | frontend/src/api/workforce.ts |
| POST | `/api/v1/workforce/tasks/{task_id}/recommend-workforce` | ui-advanced | n/a | workforce | Intentional backend surface |
| GET | `/api/v1/workforce/tasks/{task_id}/skill-matches` | ui-required | `/my-tasks` | workforce | frontend/src/api/workforce.ts |
| GET | `/api/v1/workforce/tools` | ui-required | `/my-tasks` | workforce | frontend/src/api/workforce.ts |
| GET | `/api/v1/workforce/trigger-subscriptions` | ui-required | `/my-tasks` | workforce | frontend/src/api/integrations.ts |
| DELETE | `/api/v1/workforce/trigger-subscriptions/{subscription_id}` | ui-required | `/my-tasks` | workforce | frontend/src/api/integrations.ts |
| POST | `/api/v1/workforce/webhooks/gmail` | internal | n/a | workforce | Intentional backend surface |
| GET | `/api/v1/workforce/webhooks/outlook` | internal | n/a | workforce | Intentional backend surface |
| POST | `/api/v1/workforce/webhooks/outlook` | internal | n/a | workforce | Intentional backend surface |
| POST | `/api/v1/workforce/webhooks/slack` | internal | n/a | workforce | Intentional backend surface |
| POST | `/api/v1/workforce/webhooks/teams` | internal | n/a | workforce | Intentional backend surface |
| POST | `/api/v1/workforce/webhooks/telegram` | internal | n/a | workforce | Intentional backend surface |
| GET | `/api/v1/workforce/workflows` | ui-required | `/workforce-workflows` | workflows | frontend/src/api/workforce.ts |
| POST | `/api/v1/workforce/workflows` | ui-required | `/workforce-workflows` | workflows | frontend/src/api/workforce.ts |
| POST | `/api/v1/workforce/workflows/generate` | ui-required | `/workforce-workflows` | workflows | frontend/src/api/workforce.ts |
| GET | `/api/v1/workforce/workflows/runs/{run_id}` | ui-required | `/workforce-workflows` | workflows | frontend/src/api/integrations.ts |
| POST | `/api/v1/workforce/workflows/runs/{run_id}/resume` | ui-advanced | n/a | workflows | Intentional backend surface |
| GET | `/api/v1/workforce/workflows/runs/{run_id}/steps` | ui-required | `/workforce-workflows` | workflows | frontend/src/api/integrations.ts |
| GET | `/api/v1/workforce/workflows/runs/{run_id}/stream` | internal | n/a | workflows | Intentional backend surface |
| GET | `/api/v1/workforce/workflows/{workflow_id}` | ui-required | `/workforce-workflows` | workflows | frontend/src/api/workforce.ts |
| GET | `/api/v1/workforce/workflows/{workflow_id}/diff` | ui-required | `/workforce-workflows` | workflows | frontend/src/api/workforce.ts |
| PATCH | `/api/v1/workforce/workflows/{workflow_id}/draft` | ui-required | `/workforce-workflows` | workflows | frontend/src/api/workforce.ts |
| GET | `/api/v1/workforce/workflows/{workflow_id}/environments` | ui-required | `/workforce-workflows` | workflows | frontend/src/api/workforce.ts |
| GET | `/api/v1/workforce/workflows/{workflow_id}/environments/{environment}` | ui-advanced | n/a | workflows | Intentional backend surface |
| POST | `/api/v1/workforce/workflows/{workflow_id}/environments/{environment}/diff` | ui-required | `/workforce-workflows` | workflows | frontend/src/api/workforce.ts |
| GET | `/api/v1/workforce/workflows/{workflow_id}/environments/{environment}/history` | ui-required | `/workforce-workflows` | workflows | frontend/src/api/workforce.ts |
| POST | `/api/v1/workforce/workflows/{workflow_id}/environments/{environment}/promote` | ui-required | `/workforce-workflows` | workflows | frontend/src/api/workforce.ts |
| POST | `/api/v1/workforce/workflows/{workflow_id}/environments/{environment}/rollback` | ui-required | `/workforce-workflows` | workflows | frontend/src/api/workforce.ts |
| POST | `/api/v1/workforce/workflows/{workflow_id}/publish` | ui-required | `/workforce-workflows` | workflows | frontend/src/api/workforce.ts |
| POST | `/api/v1/workforce/workflows/{workflow_id}/rollback` | ui-required | `/workforce-workflows` | workflows | frontend/src/api/workforce.ts |
| POST | `/api/v1/workforce/workflows/{workflow_id}/runs` | ui-required | `/workforce-workflows` | workflows | frontend/src/api/workforce.ts |
| POST | `/api/v1/workforce/workflows/{workflow_id}/test-runs` | ui-required | `/workforce-workflows` | workflows | frontend/src/api/workforce.ts |
| GET | `/api/v1/workforce/workflows/{workflow_id}/validate` | ui-required | `/workforce-workflows` | workflows | frontend/src/api/workforce.ts |
| GET | `/api/v1/workforce/workflows/{workflow_id}/versions` | ui-required | `/workforce-workflows` | workflows | frontend/src/api/workforce.ts |
| GET | `/health/live` | internal | n/a | api | Intentional backend surface |
| GET | `/health/ready` | internal | n/a | api | Intentional backend surface |
| GET | `/health/version` | internal | n/a | api | Intentional backend surface |
| GET | `/metrics` | internal | n/a | api | Intentional backend surface |
| POST | `/webhooks/github` | internal | n/a | api | Intentional backend surface |
| POST | `/webhooks/incidents` | internal | n/a | api | Intentional backend surface |
