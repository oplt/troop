import type { Approval } from "../../api/orchestration";
import { humanizeKey } from "../../utils/formatters";
import { normalizeEmailApproval } from "../approvals/emailApproval";

export function emailConsequenceLine(approval: {
    approval_type: string;
    payload: Record<string, unknown>;
}): string | null {
    const email = normalizeEmailApproval(approval.payload, approval.approval_type);
    if (!email.isEmail) return null;
    const recipients =
        email.draft.to.length > 0
            ? email.draft.to
            : email.incoming.to.map((item) => item.email).filter(Boolean);
    if (recipients.length === 0) return "Sends email (recipients not set yet).";
    return `Sends email to ${recipients.join(", ")}`;
}

export function describeAction(approval: { approval_type: string; payload: Record<string, unknown> }): string {
    const { approval_type: type, payload } = approval;
    const operation = String(payload.operation ?? payload.action ?? payload.tool_key ?? "");
    if (type.includes("email") || type.includes("gmail") || operation.includes("gmail")) {
        return operation.includes("send") ? "Approve and send email draft" : "Review email action";
    }
    switch (type) {
        case "github_comment":
            return "Post a comment to GitHub";
        case "rule_escalation": {
            const condition = payload?.condition as string | undefined;
            if (condition === "cost_exceeds_usd") {
                const cost = payload?.cost_usd as number | undefined;
                return cost != null ? `Cost threshold exceeded ($${cost.toFixed(2)})` : "Cost threshold exceeded";
            }
            if (condition === "stuck_for_minutes") {
                const mins = payload?.elapsed_minutes as number | undefined;
                return mins != null ? `Task stalled for ${mins} minutes` : "Task stalled";
            }
            if (condition === "no_consensus_after_rounds") {
                const rounds = payload?.rounds_completed as number | undefined;
                return rounds != null ? `No consensus after ${rounds} rounds` : "No consensus reached";
            }
            return "Escalation rule triggered";
        }
        case "task_escalation": {
            const reason = payload?.reason as string | undefined;
            return reason ?? "Task escalated to human";
        }
        case "agent_memory_write":
            return "Write to agent memory";
        case "post_to_github":
            return "Post results to GitHub";
        case "open_pr":
            return "Open a pull request";
        case "mark_complete":
            return "Mark task as complete";
        case "write_memory":
            return "Write to project memory";
        case "use_expensive_model":
            return "Use an expensive model";
        case "run_tool":
            return "Run an external tool";
        default:
            return humanizeKey(type);
    }
}

export function parseDateBoundary(value: string, endOfDay: boolean): number | null {
    if (!value.trim()) return null;
    const t = new Date(value + (endOfDay ? "T23:59:59.999Z" : "T00:00:00.000Z"));
    return Number.isNaN(t.getTime()) ? null : t.getTime();
}

export type { Approval };
