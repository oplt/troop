export type EmailAddress = { name?: string; email: string };

export type EmailApprovalView = {
    isEmail: boolean;
    incoming: {
        from: EmailAddress | null;
        to: EmailAddress[];
        subject: string;
        body: string;
        received_at: string | null;
    };
    draft: {
        to: string[];
        cc: string[];
        bcc: string[];
        subject: string;
        body_text: string;
    };
    risk: string;
    warnings: string[];
    context: Array<{ title: string; source?: string }>;
    agent: string | null;
    workflow: string | null;
    project: string | null;
    task: string | null;
    stale: boolean;
};

function record(value: unknown): Record<string, unknown> {
    return value && typeof value === "object" && !Array.isArray(value)
        ? value as Record<string, unknown>
        : {};
}

function address(value: unknown): EmailAddress | null {
    if (typeof value === "string") return value.trim() ? { email: value } : null;
    const raw = record(value);
    const email = String(raw.email ?? raw.address ?? "").trim();
    return email ? { email, name: typeof raw.name === "string" ? raw.name : undefined } : null;
}

function addressList(value: unknown): EmailAddress[] {
    return (Array.isArray(value) ? value : value ? [value] : [])
        .map(address)
        .filter((item): item is EmailAddress => item !== null);
}

function stringList(value: unknown): string[] {
    return (Array.isArray(value) ? value : typeof value === "string" ? value.split(",") : [])
        .map((item) => typeof item === "string" ? item.trim() : address(item)?.email ?? "")
        .filter(Boolean);
}

export function normalizeEmailApproval(payload: Record<string, unknown>, approvalType = ""): EmailApprovalView {
    const email = record(payload.email ?? payload.incoming_email ?? payload.incoming);
    const draft = record(
        payload.draft ?? payload.proposed_reply ?? payload.draft_arguments ?? payload.arguments,
    );
    const contextRaw = payload.context ?? payload.sources ?? [];
    const context = (Array.isArray(contextRaw) ? contextRaw : []).map((item) => {
        if (typeof item === "string") return { title: item };
        const row = record(item);
        return {
            title: String(row.title ?? row.summary ?? row.label ?? "Context source"),
            source: typeof row.source === "string" ? row.source : undefined,
        };
    });
    const operation = String(
        payload.operation ?? payload.action ?? payload.action_key ?? payload.tool_key ?? "",
    );
    return {
        isEmail: approvalType.includes("email") || approvalType.includes("gmail") || operation.includes("gmail") || Object.keys(email).length > 0 || Object.keys(draft).some((key) => ["subject", "body", "body_text", "to"].includes(key)),
        incoming: {
            from: address(email.from ?? payload.from),
            to: addressList(email.to),
            subject: String(email.subject ?? payload.incoming_subject ?? ""),
            body: String(email.text_body ?? email.body_text ?? email.body ?? payload.incoming_body ?? ""),
            received_at: typeof email.received_at === "string" ? email.received_at : null,
        },
        draft: {
            to: stringList(draft.to ?? payload.to),
            cc: stringList(draft.cc ?? payload.cc),
            bcc: stringList(draft.bcc ?? payload.bcc),
            subject: String(draft.subject ?? payload.subject ?? ""),
            body_text: String(draft.body_text ?? draft.body ?? payload.body_text ?? payload.body ?? ""),
        },
        risk: String(payload.risk_level ?? payload.risk ?? "high"),
        warnings: stringList(payload.warnings),
        context,
        agent: typeof payload.agent_name === "string" ? payload.agent_name : typeof payload.agent === "string" ? payload.agent : null,
        workflow: typeof payload.workflow_name === "string" ? payload.workflow_name : typeof payload.workflow === "string" ? payload.workflow : null,
        project: typeof payload.project_name === "string" ? payload.project_name : null,
        task: typeof payload.task_name === "string" ? payload.task_name : null,
        stale: ["stale", "invalidated"].includes(String(payload.draft_status ?? payload.status ?? "")),
    };
}
