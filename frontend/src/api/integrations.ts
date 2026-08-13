import { apiFetch } from "./client";

export type ConnectorOperationType = "trigger" | "search" | "read" | "action";

export type ConnectorDefinition = {
    id: string;
    slug: string;
    name: string;
    description: string;
    provider_type: string;
    config_schema_json: Record<string, unknown>;
    metadata_json: Record<string, unknown>;
};

export type ConnectorInstallation = {
    id: string;
    connector_definition_id: string;
    owner_id: string;
    company_id: string | null;
    name: string;
    status: string;
    config_json: Record<string, unknown>;
    metadata_json: Record<string, unknown>;
    created_at: string | null;
    updated_at: string | null;
};

export type ConnectorOperation = {
    id: string;
    connector_definition_id: string;
    slug: string;
    operation_type: ConnectorOperationType;
    name: string;
    description: string;
    input_schema_json: Record<string, unknown>;
    output_schema_json: Record<string, unknown>;
    risk_level: string;
    requires_approval: boolean;
    required_scopes: string[];
    metadata_json: Record<string, unknown>;
};

export type ConnectorStatus = {
    provider: "gmail" | "telegram";
    status: string;
    installation_id: string | null;
    account_label: string | null;
    granted_scopes: string[];
    required_scopes: string[];
    last_successful_event_at: string | null;
    expires_at: string | null;
    error: string | null;
    metadata: Record<string, unknown>;
};

export type TelegramLink = {
    binding_id: string;
    deep_link_url: string;
    expires_at: string;
};

export type TriggerSubscription = {
    id: string;
    connector_installation_id: string;
    workflow_id: string;
    workflow_version_id: string | null;
    node_id: string;
    provider: string;
    status: string;
    expires_at: string | null;
    last_event_at: string | null;
    error: string | null;
    metadata_json: Record<string, unknown>;
};

export type WorkflowStepRun = {
    id: string;
    workflow_run_id: string;
    node_id: string;
    node_type: string;
    status: string;
    input_json: Record<string, unknown>;
    output_json: Record<string, unknown>;
    error: string | null;
    retry_count: number;
    started_at: string | null;
    finished_at: string | null;
    created_at: string;
};

export type WorkflowRun = {
    id: string;
    workflow_id: string;
    workflow_version_id: string;
    project_id: string | null;
    task_id: string | null;
    status: string;
    current_node_id: string | null;
    context_json: Record<string, unknown>;
    result_json: Record<string, unknown>;
    created_at: string;
    updated_at: string;
    steps: WorkflowStepRun[];
};

type UnknownRecord = Record<string, unknown>;

function record(value: unknown): UnknownRecord {
    return value && typeof value === "object" && !Array.isArray(value)
        ? value as UnknownRecord
        : {};
}

function strings(value: unknown): string[] {
    return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function nullableString(value: unknown): string | null {
    return typeof value === "string" && value.trim() ? value : null;
}

function unwrapList(value: unknown): UnknownRecord[] {
    if (Array.isArray(value)) return value.map(record);
    const body = record(value);
    for (const key of ["items", "results", "data", "definitions", "installations", "operations", "subscriptions", "steps"]) {
        if (Array.isArray(body[key])) return (body[key] as unknown[]).map(record);
    }
    return [];
}

export function normalizeConnectorDefinition(value: unknown): ConnectorDefinition {
    const raw = record(value);
    return {
        id: String(raw.id ?? ""),
        slug: String(raw.slug ?? raw.key ?? ""),
        name: String(raw.name ?? raw.slug ?? ""),
        description: String(raw.description ?? ""),
        provider_type: String(raw.provider_type ?? raw.provider ?? "native"),
        config_schema_json: record(raw.config_schema_json ?? raw.config_schema),
        metadata_json: record(raw.metadata_json ?? raw.metadata),
    };
}

export function normalizeConnectorInstallation(value: unknown): ConnectorInstallation {
    const raw = record(value);
    return {
        id: String(raw.id ?? ""),
        connector_definition_id: String(raw.connector_definition_id ?? ""),
        owner_id: String(raw.owner_id ?? ""),
        company_id: nullableString(raw.company_id),
        name: String(raw.name ?? raw.account_label ?? "Connection"),
        status: String(raw.status ?? "disconnected"),
        // The API must redact secrets. These objects are only used for safe display metadata.
        config_json: record(raw.config_json ?? raw.config),
        metadata_json: record(raw.metadata_json ?? raw.metadata),
        created_at: nullableString(raw.created_at),
        updated_at: nullableString(raw.updated_at),
    };
}

export function normalizeConnectorOperation(value: unknown): ConnectorOperation {
    const raw = record(value);
    return {
        id: String(raw.id ?? raw.slug ?? ""),
        connector_definition_id: String(raw.connector_definition_id ?? ""),
        slug: String(raw.slug ?? raw.key ?? ""),
        operation_type: (["trigger", "search", "read", "action"].includes(String(raw.operation_type))
            ? raw.operation_type
            : "action") as ConnectorOperationType,
        name: String(raw.name ?? raw.slug ?? ""),
        description: String(raw.description ?? ""),
        input_schema_json: record(raw.input_schema_json ?? raw.input_schema),
        output_schema_json: record(raw.output_schema_json ?? raw.output_schema),
        risk_level: String(raw.risk_level ?? "low"),
        requires_approval: Boolean(raw.requires_approval),
        required_scopes: strings(raw.required_scopes ?? raw.required_scopes_json),
        metadata_json: record(raw.metadata_json ?? raw.metadata),
    };
}

export function normalizeConnectorStatus(provider: "gmail" | "telegram", value: unknown): ConnectorStatus {
    const raw = record(value);
    const installation = record(raw.installation);
    return {
        provider,
        status: String(raw.status ?? installation.status ?? "disconnected"),
        installation_id: nullableString(raw.installation_id ?? installation.id),
        account_label: nullableString(raw.account_label ?? raw.email ?? raw.username ?? installation.name),
        granted_scopes: strings(raw.granted_scopes ?? raw.scopes),
        required_scopes: strings(raw.required_scopes),
        last_successful_event_at: nullableString(raw.last_successful_event_at ?? raw.last_event_at),
        expires_at: nullableString(raw.expires_at ?? raw.token_expires_at),
        error: nullableString(raw.error ?? raw.last_error),
        metadata: record(raw.metadata),
    };
}

export async function listConnectorDefinitions(): Promise<ConnectorDefinition[]> {
    return unwrapList(await apiFetch<unknown>("/workforce/connectors/definitions"))
        .map(normalizeConnectorDefinition);
}

export async function listConnectorInstallations(): Promise<ConnectorInstallation[]> {
    return unwrapList(await apiFetch<unknown>("/workforce/connectors/installations"))
        .map(normalizeConnectorInstallation);
}

export async function listConnectorOperations(definitionId?: string): Promise<ConnectorOperation[]> {
    const query = definitionId ? `?connector_definition_id=${encodeURIComponent(definitionId)}` : "";
    return unwrapList(await apiFetch<unknown>(`/workforce/connector-operations${query}`))
        .map(normalizeConnectorOperation);
}

export async function testConnectorInstallation(id: string): Promise<{ ok: boolean; error?: string }> {
    return apiFetch(`/workforce/connectors/installations/${encodeURIComponent(id)}/test`, { method: "POST" });
}

export async function disconnectGmail(id: string): Promise<void> {
    return apiFetch(`/workforce/connectors/gmail/${encodeURIComponent(id)}/disconnect`, {
        method: "POST",
    });
}

export async function getGmailAuthorizeUrl(
    redirectAfter = "/integrations",
): Promise<{ authorization_url: string }> {
    return apiFetch("/workforce/connectors/gmail/authorize", {
        method: "POST",
        body: JSON.stringify({ redirect_after: redirectAfter }),
    });
}

export async function getGmailStatus(): Promise<ConnectorStatus> {
    return normalizeConnectorStatus(
        "gmail",
        await apiFetch<unknown>("/workforce/connectors/gmail/status"),
    );
}

export async function getTelegramStatus(): Promise<ConnectorStatus> {
    return normalizeConnectorStatus(
        "telegram",
        await apiFetch<unknown>("/workforce/connectors/telegram/status"),
    );
}

export async function createTelegramLink(connectorInstallationId: string): Promise<TelegramLink> {
    return apiFetch("/workforce/connectors/telegram/link", {
        method: "POST",
        body: JSON.stringify({ connector_installation_id: connectorInstallationId }),
    });
}

export async function configureTelegramWebhook(
    connectorInstallationId: string,
): Promise<{ configured: boolean }> {
    return apiFetch(
        `/workforce/connectors/telegram/${encodeURIComponent(connectorInstallationId)}/configure-webhook`,
        { method: "POST" },
    );
}

export async function unlinkTelegram(bindingId: string): Promise<void> {
    return apiFetch(
        `/workforce/connectors/telegram/bindings/${encodeURIComponent(bindingId)}`,
        { method: "DELETE" },
    );
}

export async function listTriggerSubscriptions(): Promise<TriggerSubscription[]> {
    const rows = unwrapList(await apiFetch<unknown>("/workforce/trigger-subscriptions"));
    return rows.map((raw) => ({
        id: String(raw.id ?? ""),
        connector_installation_id: String(raw.connector_installation_id ?? ""),
        workflow_id: String(raw.workflow_id ?? ""),
        workflow_version_id: nullableString(raw.workflow_version_id),
        node_id: String(raw.node_id ?? ""),
        provider: String(raw.provider ?? ""),
        status: String(raw.status ?? "unknown"),
        expires_at: nullableString(raw.expires_at),
        last_event_at: nullableString(raw.last_event_at),
        error: nullableString(raw.error ?? raw.last_error),
        metadata_json: record(raw.metadata_json ?? raw.metadata),
    }));
}

export async function renewTriggerSubscription(id: string): Promise<TriggerSubscription> {
    return apiFetch(`/workforce/trigger-subscriptions/${encodeURIComponent(id)}/renew`, { method: "POST" });
}

export async function disableTriggerSubscription(id: string): Promise<TriggerSubscription> {
    return apiFetch(`/workforce/trigger-subscriptions/${encodeURIComponent(id)}`, {
        method: "DELETE",
    });
}

export async function getWorkflowRun(id: string): Promise<WorkflowRun> {
    return apiFetch(`/workforce/workflows/runs/${encodeURIComponent(id)}`);
}

export async function listWorkflowRunSteps(id: string): Promise<WorkflowStepRun[]> {
    return unwrapList(
        await apiFetch<unknown>(
            `/workforce/workflows/runs/${encodeURIComponent(id)}/steps`,
        ),
    )
        .map((raw) => ({
            id: String(raw.id ?? ""),
            workflow_run_id: String(raw.workflow_run_id ?? id),
            node_id: String(raw.node_id ?? ""),
            node_type: String(raw.node_type ?? ""),
            status: String(raw.status ?? "pending"),
            input_json: record(raw.input_json ?? raw.input),
            output_json: record(raw.output_json ?? raw.output),
            error: nullableString(raw.error),
            retry_count: Number(raw.retry_count ?? raw.attempts ?? 0),
            started_at: nullableString(raw.started_at),
            finished_at: nullableString(raw.finished_at ?? raw.completed_at),
            created_at: String(raw.created_at ?? ""),
        }));
}

export async function editEmailApprovalPayload(
    approvalId: string,
    payload: { subject: string; body_text: string; to: string[]; cc: string[]; bcc: string[] },
): Promise<unknown> {
    return apiFetch(`/orchestration/approvals/${encodeURIComponent(approvalId)}/payload`, {
        method: "PATCH",
        body: JSON.stringify(payload),
    });
}

export async function requestApprovalChanges(approvalId: string, reason: string): Promise<unknown> {
    return apiFetch(`/orchestration/approvals/${encodeURIComponent(approvalId)}/request-changes`, {
        method: "POST",
        body: JSON.stringify({ reason }),
    });
}
