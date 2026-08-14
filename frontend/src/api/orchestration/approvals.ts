import { apiFetch } from "../client";

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

export async function listApprovals(): Promise<Approval[]> {
    return apiFetch("/orchestration/approvals");
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
