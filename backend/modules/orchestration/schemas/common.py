from typing import Literal

TaskStatus = Literal[
    "backlog",
    "queued",
    "planned",
    "in_progress",
    "blocked",
    "needs_review",
    "approved",
    "completed",
    "failed",
    "synced_to_github",
    "archived",
]
TaskPriority = Literal["low", "normal", "high", "urgent"]
RunMode = Literal["single_agent", "manager_worker", "brainstorm", "review", "debate"]
HierarchyRelationship = Literal["delegates_to", "reviews", "escalates_to", "collaborates_with"]
HierarchyRoutingMode = Literal[
    "capability_based",
    "priority_sla",
    "sla_priority",
    "cost_aware",
    "model_availability",
    "user_pinned",
    "throughput",
]
HierarchyExecutionMode = Literal["single_agent", "manager_worker", "debate"]
BrainstormMode = Literal[
    "exploration",
    "solution_design",
    "code_review",
    "incident_triage",
    "root_cause",
    "architecture_proposal",
]
BrainstormOutputType = Literal[
    "adr",
    "implementation_plan",
    "test_plan",
    "issue_reply_draft",
    "risk_register",
]
