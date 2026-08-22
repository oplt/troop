export const DEFAULT_AGENT_MARKDOWN = `---
name: New Specialist
role: specialist
capabilities: [planning]
tools_allowed: [fs_read]
permissions: read-only
escalation_path: manager
task_filters: [triage]
model:
  provider: openai
  model: gpt-4.1
memory_policy:
  scope: project-only
budget:
  token_budget: 4000
  time_budget_seconds: 300
  retry_budget: 1
output_schema: checklist
---

# Mission

Describe the work this agent owns.

# Rules

- Stay within the assigned task filters.

# Output Contract

Return a concise checklist with evidence and blockers.`;

export const TOOL_ALIASES: Record<string, string> = {
    file_read_stub: "fs_read",
    web_search_stub: "web_search",
    python_analysis_stub: "code_execute",
    github_issue_stub: "github_comment",
    geospatial_analysis_stub: "code_execute",
};

export type AgentProfileForm = {
    name: string;
    slug: string;
    role: string;
    description: string;
    capabilities: string;
    allowed_tools: string[];
    permissions: string;
    escalation_path: string;
    task_filters: string;
    provider: string;
    model: string;
    fallback_model: string;
    max_context: string;
    max_tokens: string;
    temperature: string;
    reasoning_level: string;
    reasoning_effort: string;
    tool_calling: boolean;
    structured_output: boolean;
    timeout_seconds: string;
    retry_count: string;
    memory_scope: string;
    token_budget: string;
    time_budget_seconds: string;
    retry_budget: string;
    budget_cap_usd: string;
    output_format: string;
};

export type AgentValidationState = {
    errors: string[];
    warnings: string[];
    ready: boolean;
};

export type AgentEditorTab = "profile" | "skills" | "tools" | "memory" | "runs" | "evaluation";
