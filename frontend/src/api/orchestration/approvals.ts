import { apiFetch } from "../client";
import { appendCursorParams, assertCursorPage, type CursorPage, type CursorToken } from "../pagination";

export type ApprovalListItem = {
    id: string;
    project_id: string | null;
    task_id: string | null;
    run_id: string | null;
    issue_link_id: string | null;
    approval_type: string;
    status: string;
    reason: string | null;
    effect_hash: string | null;
    effect_version: number;
    expires_at: string | null;
    created_at: string;
    resolved_at: string | null;
};

export type Approval = {
    id: string;
    project_id: string | null;
    task_id: string | null;
    run_id: string | null;
    issue_link_id: string | null;
    requested_by_user_id: string | null;
    approved_by_user_id: string | null;
    approval_type: string;
    status: string;
    reason: string | null;
    payload: Record<string, unknown>;
    effect_hash: string | null;
    effect_version: number;
    precondition_fingerprint: string | null;
    expires_at: string | null;
    proposed_effect: Record<string, unknown> | null;
    workspace_id: string | null;
    eligible_approvers: Array<Record<string, unknown>>;
    routing_snapshot: Record<string, unknown>;
    decided_eligibility_reason: string | null;
    due_at: string | null;
    sla_policy: Record<string, unknown>;
    delegations: Array<Record<string, unknown>>;
    escalation_state: Record<string, unknown>;
    created_at: string;
    resolved_at: string | null;
};

export type HITLAuditLog = {
    id: string;
    user_id: string | null;
    action: string;
    resource_type: string | null;
    resource_id: string | null;
    metadata: Record<string, unknown>;
    created_at: string;
};

export async function listApprovalsPage(
    options: { limit?: number; cursor?: CursorToken | null } = {},
): Promise<CursorPage<ApprovalListItem>> {
    const params = new URLSearchParams();
    appendCursorParams(params, options);
    const query = params.toString();
    const payload = await apiFetch<unknown>(`/orchestration/approvals${query ? `?${query}` : ""}`);
    return assertCursorPage<ApprovalListItem>(payload, "/orchestration/approvals");
}

export async function listApprovals(
    options: { limit?: number; cursor?: CursorToken | null } = {},
): Promise<ApprovalListItem[]> {
    const page = await listApprovalsPage(options);
    return page.items;
}

export async function getApproval(approvalId: string): Promise<Approval> {
    return apiFetch(`/orchestration/approvals/${approvalId}`);
}

export async function listHITLAuditLogs(limit = 100): Promise<HITLAuditLog[]> {
    return apiFetch(`/orchestration/hitl/audit-logs?limit=${Math.max(1, Math.min(limit, 200))}`);
}

/** Process-global counters + `_rollup` (hit rates, histograms, promotion/conflict summaries). */

export async function decideApproval(approvalId: string, payload: { status: "approved" | "rejected"; reason?: string }): Promise<Approval> {
    return apiFetch(`/orchestration/approvals/${approvalId}`, { method: "POST", body: JSON.stringify(payload) });
}

export async function getPendingApprovalsCount(): Promise<{ count: number }> {
    return apiFetch("/orchestration/approvals/pending-count");
}
