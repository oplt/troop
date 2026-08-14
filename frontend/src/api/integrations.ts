import { apiFetch } from "./client";

export type ConnectorOperationType = "trigger" | "search" | "read" | "action";

export type ConnectorScopeManifest = {
    scope: string;
    label: string;
    description: string;
    required_for: string[];
};

export type ConnectorOperationManifest = {
    slug: string;
    name: string;
    description: string;
    operation_kind: string;
    input_schema: Record<string, unknown>;
    output_schema: Record<string, unknown>;
    risk_level: string;
    requires_approval: boolean;
    required_scopes: string[];
    parallel_safe: boolean;
    idempotency_strategy: string;
};

export type ConnectorManifest = {
    provider_slug: string;
    version: string;
    name: string;
    description: string;
    provider_type: string;
    auth: {
        type: string;
        scopes: ConnectorScopeManifest[];
        config_schema: Record<string, unknown>;
        reauthorization: string;
        pkce_required: boolean;
    };
    triggers: ConnectorOperationManifest[];
    actions: ConnectorOperationManifest[];
    webhook: Record<string, unknown> | null;
    health: Record<string, unknown> | null;
    rate_limits: Record<string, unknown> | null;
    metadata: Record<string, unknown>;
};

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
    environment: string;
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
    provider: "gmail" | "outlook" | "google_calendar" | "microsoft_calendar" | "google_drive" | "microsoft_drive" | "jira" | "linear" | "hubspot" | "salesforce" | "telegram" | "slack" | "teams";
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

function normalizeScopeManifest(value: unknown): ConnectorScopeManifest {
    const raw = record(value);
    return {
        scope: String(raw.scope ?? ""),
        label: String(raw.label ?? raw.scope ?? ""),
        description: String(raw.description ?? ""),
        required_for: strings(raw.required_for),
    };
}

function normalizeOperationManifest(value: unknown): ConnectorOperationManifest {
    const raw = record(value);
    const governance = record(raw.governance);
    return {
        slug: String(raw.slug ?? ""),
        name: String(raw.name ?? raw.slug ?? ""),
        description: String(raw.description ?? ""),
        operation_kind: String(raw.operation_kind ?? raw.operation_type ?? "action"),
        input_schema: record(raw.input_schema ?? raw.input_schema_json),
        output_schema: record(raw.output_schema ?? raw.output_schema_json),
        risk_level: String(raw.risk_level ?? "low"),
        requires_approval: Boolean(raw.requires_approval),
        required_scopes: strings(raw.required_scopes ?? raw.required_scopes_json),
        parallel_safe: Boolean(raw.parallel_safe ?? governance.parallel_safe),
        idempotency_strategy: String(raw.idempotency_strategy ?? governance.idempotency_strategy ?? "none"),
    };
}

export function normalizeConnectorManifest(value: unknown): ConnectorManifest {
    const raw = record(value);
    const auth = record(raw.auth);
    return {
        provider_slug: String(raw.provider_slug ?? raw.slug ?? ""),
        version: String(raw.version ?? "1.0.0"),
        name: String(raw.name ?? raw.provider_slug ?? ""),
        description: String(raw.description ?? ""),
        provider_type: String(raw.provider_type ?? "native"),
        auth: {
            type: String(auth.type ?? "none"),
            scopes: Array.isArray(auth.scopes) ? auth.scopes.map(normalizeScopeManifest) : [],
            config_schema: record(auth.config_schema ?? auth.config_schema_json),
            reauthorization: String(auth.reauthorization ?? "manual"),
            pkce_required: Boolean(auth.pkce_required),
        },
        triggers: Array.isArray(raw.triggers) ? raw.triggers.map(normalizeOperationManifest) : [],
        actions: Array.isArray(raw.actions) ? raw.actions.map(normalizeOperationManifest) : [],
        webhook: raw.webhook && typeof raw.webhook === "object" ? record(raw.webhook) : null,
        health: raw.health && typeof raw.health === "object" ? record(raw.health) : null,
        rate_limits: raw.rate_limits && typeof raw.rate_limits === "object" ? record(raw.rate_limits) : null,
        metadata: record(raw.metadata ?? raw.metadata_json),
    };
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
        environment: String(raw.environment ?? "dev"),
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

export function normalizeConnectorStatus(
    provider: "gmail" | "outlook" | "google_calendar" | "microsoft_calendar" | "google_drive" | "microsoft_drive" | "jira" | "linear" | "telegram" | "slack" | "teams",
    value: unknown,
): ConnectorStatus {
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

export async function listConnectorManifests(): Promise<ConnectorManifest[]> {
    return unwrapList(await apiFetch<unknown>("/workforce/connectors/manifests"))
        .map(normalizeConnectorManifest);
}

export async function getConnectorManifest(providerSlug: string): Promise<ConnectorManifest> {
    return normalizeConnectorManifest(
        await apiFetch<unknown>(`/workforce/connectors/manifests/${encodeURIComponent(providerSlug)}`),
    );
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

export async function getOutlookAuthorizeUrl(
    redirectAfter = "/integrations",
): Promise<{ authorization_url: string }> {
    return apiFetch("/workforce/connectors/outlook/authorize", {
        method: "POST",
        body: JSON.stringify({ redirect_after: redirectAfter }),
    });
}

export async function getOutlookStatus(): Promise<ConnectorStatus> {
    return normalizeConnectorStatus(
        "outlook",
        await apiFetch<unknown>("/workforce/connectors/outlook/status"),
    );
}

export async function disconnectOutlook(id: string): Promise<void> {
    return apiFetch(`/workforce/connectors/outlook/${encodeURIComponent(id)}/disconnect`, {
        method: "POST",
    });
}

export async function getGoogleCalendarAuthorizeUrl(
    redirectAfter = "/integrations",
): Promise<{ authorization_url: string }> {
    return apiFetch("/workforce/connectors/google_calendar/authorize", {
        method: "POST",
        body: JSON.stringify({ redirect_after: redirectAfter }),
    });
}

export async function getGoogleCalendarStatus(): Promise<ConnectorStatus> {
    return normalizeConnectorStatus(
        "google_calendar",
        await apiFetch<unknown>("/workforce/connectors/google_calendar/status"),
    );
}

export async function disconnectGoogleCalendar(id: string): Promise<void> {
    return apiFetch(`/workforce/connectors/google_calendar/${encodeURIComponent(id)}/disconnect`, {
        method: "POST",
    });
}

export async function getMicrosoftCalendarAuthorizeUrl(
    redirectAfter = "/integrations",
): Promise<{ authorization_url: string }> {
    return apiFetch("/workforce/connectors/microsoft_calendar/authorize", {
        method: "POST",
        body: JSON.stringify({ redirect_after: redirectAfter }),
    });
}

export async function getMicrosoftCalendarStatus(): Promise<ConnectorStatus> {
    return normalizeConnectorStatus(
        "microsoft_calendar",
        await apiFetch<unknown>("/workforce/connectors/microsoft_calendar/status"),
    );
}

export async function disconnectMicrosoftCalendar(id: string): Promise<void> {
    return apiFetch(`/workforce/connectors/microsoft_calendar/${encodeURIComponent(id)}/disconnect`, {
        method: "POST",
    });
}

export async function getGoogleDriveAuthorizeUrl(
    redirectAfter = "/integrations",
): Promise<{ authorization_url: string }> {
    return apiFetch("/workforce/connectors/google_drive/authorize", {
        method: "POST",
        body: JSON.stringify({ redirect_after: redirectAfter }),
    });
}

export async function getGoogleDriveStatus(): Promise<ConnectorStatus> {
    return normalizeConnectorStatus(
        "google_drive",
        await apiFetch<unknown>("/workforce/connectors/google_drive/status"),
    );
}

export async function disconnectGoogleDrive(id: string): Promise<void> {
    return apiFetch(`/workforce/connectors/google_drive/${encodeURIComponent(id)}/disconnect`, {
        method: "POST",
    });
}

export async function getMicrosoftDriveAuthorizeUrl(
    redirectAfter = "/integrations",
): Promise<{ authorization_url: string }> {
    return apiFetch("/workforce/connectors/microsoft_drive/authorize", {
        method: "POST",
        body: JSON.stringify({ redirect_after: redirectAfter }),
    });
}

export async function getMicrosoftDriveStatus(): Promise<ConnectorStatus> {
    return normalizeConnectorStatus(
        "microsoft_drive",
        await apiFetch<unknown>("/workforce/connectors/microsoft_drive/status"),
    );
}

export async function disconnectMicrosoftDrive(id: string): Promise<void> {
    return apiFetch(`/workforce/connectors/microsoft_drive/${encodeURIComponent(id)}/disconnect`, {
        method: "POST",
    });
}

export async function getJiraAuthorizeUrl(
    redirectAfter = "/integrations",
): Promise<{ authorization_url: string }> {
    return apiFetch("/workforce/connectors/jira/authorize", {
        method: "POST",
        body: JSON.stringify({ redirect_after: redirectAfter }),
    });
}

export async function getJiraStatus(): Promise<ConnectorStatus> {
    return normalizeConnectorStatus(
        "jira",
        await apiFetch<unknown>("/workforce/connectors/jira/status"),
    );
}

export async function disconnectJira(id: string): Promise<void> {
    return apiFetch(`/workforce/connectors/jira/${encodeURIComponent(id)}/disconnect`, {
        method: "POST",
    });
}

export async function getLinearAuthorizeUrl(
    redirectAfter = "/integrations",
): Promise<{ authorization_url: string }> {
    return apiFetch("/workforce/connectors/linear/authorize", {
        method: "POST",
        body: JSON.stringify({ redirect_after: redirectAfter }),
    });
}

export async function getLinearStatus(): Promise<ConnectorStatus> {
    return normalizeConnectorStatus(
        "linear",
        await apiFetch<unknown>("/workforce/connectors/linear/status"),
    );
}

export async function disconnectLinear(id: string): Promise<void> {
    return apiFetch(`/workforce/connectors/linear/${encodeURIComponent(id)}/disconnect`, {
        method: "POST",
    });
}

export async function getHubSpotAuthorizeUrl(
    redirectAfter = "/integrations",
): Promise<{ authorization_url: string }> {
    return apiFetch("/workforce/connectors/hubspot/authorize", {
        method: "POST",
        body: JSON.stringify({ redirect_after: redirectAfter }),
    });
}

export async function getHubSpotStatus(): Promise<ConnectorStatus> {
    return normalizeConnectorStatus(
        "hubspot",
        await apiFetch<unknown>("/workforce/connectors/hubspot/status"),
    );
}

export async function disconnectHubSpot(id: string): Promise<void> {
    return apiFetch(`/workforce/connectors/hubspot/${encodeURIComponent(id)}/disconnect`, {
        method: "POST",
    });
}

export async function getSalesforceAuthorizeUrl(
    redirectAfter = "/integrations",
): Promise<{ authorization_url: string }> {
    return apiFetch("/workforce/connectors/salesforce/authorize", {
        method: "POST",
        body: JSON.stringify({ redirect_after: redirectAfter }),
    });
}

export async function getSalesforceStatus(): Promise<ConnectorStatus> {
    return normalizeConnectorStatus(
        "salesforce",
        await apiFetch<unknown>("/workforce/connectors/salesforce/status"),
    );
}

export async function disconnectSalesforce(id: string): Promise<void> {
    return apiFetch(`/workforce/connectors/salesforce/${encodeURIComponent(id)}/disconnect`, {
        method: "POST",
    });
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

export async function getSlackStatus(): Promise<ConnectorStatus> {
    return normalizeConnectorStatus(
        "slack",
        await apiFetch<unknown>("/workforce/connectors/slack/status"),
    );
}

export async function getSlackAuthorizeUrl(
    redirectAfter = "/integrations",
): Promise<{ authorization_url: string }> {
    return apiFetch("/workforce/connectors/slack/authorize", {
        method: "POST",
        body: JSON.stringify({ redirect_after: redirectAfter }),
    });
}

export async function createSlackLink(connectorInstallationId: string): Promise<TelegramLink> {
    return apiFetch("/workforce/connectors/slack/link", {
        method: "POST",
        body: JSON.stringify({ connector_installation_id: connectorInstallationId }),
    });
}

export async function unlinkSlack(bindingId: string): Promise<void> {
    return apiFetch(
        `/workforce/connectors/slack/bindings/${encodeURIComponent(bindingId)}`,
        { method: "DELETE" },
    );
}

export async function getTeamsStatus(): Promise<ConnectorStatus> {
    return normalizeConnectorStatus(
        "teams",
        await apiFetch<unknown>("/workforce/connectors/teams/status"),
    );
}

export async function getTeamsAuthorizeUrl(
    redirectAfter = "/integrations",
): Promise<{ authorization_url: string }> {
    return apiFetch("/workforce/connectors/teams/authorize", {
        method: "POST",
        body: JSON.stringify({ redirect_after: redirectAfter }),
    });
}

export async function createTeamsLink(connectorInstallationId: string): Promise<TelegramLink> {
    return apiFetch("/workforce/connectors/teams/link", {
        method: "POST",
        body: JSON.stringify({ connector_installation_id: connectorInstallationId }),
    });
}

export async function unlinkTeams(bindingId: string): Promise<void> {
    return apiFetch(
        `/workforce/connectors/teams/bindings/${encodeURIComponent(bindingId)}`,
        { method: "DELETE" },
    );
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
