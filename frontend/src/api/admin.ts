import { apiFetch, API_BASE } from "./client";

export type AdminUser = {
    id: string;
    email: string;
    full_name: string | null;
    is_verified: boolean;
    is_active: boolean;
    created_at: string;
    roles: string[];
};

export type AdminUserListResponse = {
    items: AdminUser[];
    total: number;
    page: number;
    page_size: number;
};

export async function listAdminUsers(params?: {
    page?: number;
    page_size?: number;
    search?: string;
}): Promise<AdminUserListResponse> {
    const qs = new URLSearchParams();
    if (params?.page) qs.set("page", String(params.page));
    if (params?.page_size) qs.set("page_size", String(params.page_size));
    if (params?.search) qs.set("search", params.search);
    return apiFetch(`/admin/users?${qs.toString()}`);
}

export async function updateUserStatus(
    userId: string,
    payload: { is_active: boolean }
): Promise<AdminUser> {
    return apiFetch(`/admin/users/${userId}/status`, {
        method: "PATCH",
        body: JSON.stringify(payload),
    });
}

export type SecurityPostureFinding = {
    check_id: string;
    severity: string;
    title: string;
    summary: string;
    remediation: string;
    remediation_url: string | null;
    resource_type: string | null;
    resource_id: string | null;
    metadata: Record<string, unknown>;
};

export type SecurityPostureReport = {
    generated_at: string;
    environment: string;
    summary: {
        total: number;
        critical: number;
        high: number;
        medium: number;
        low: number;
        info: number;
    };
    findings: SecurityPostureFinding[];
};

export async function getSecurityPosture(): Promise<SecurityPostureReport> {
    return apiFetch("/admin/security-posture");
}

export async function exportSecurityPosture(): Promise<Blob> {
    const response = await fetch(`${API_BASE}/admin/security-posture/export`, {
        credentials: "include",
    });
    if (!response.ok) {
        throw new Error("Failed to export security posture");
    }
    return response.blob();
}

export type AuditLogEntry = {
    id: string;
    user_id: string | null;
    workspace_id: string | null;
    action: string;
    resource_type: string | null;
    resource_id: string | null;
    ip_address: string | null;
    created_at: string;
    metadata: Record<string, unknown>;
};

export type AuditLogListResponse = {
    items: AuditLogEntry[];
    total: number;
    page: number;
    page_size: number;
};

export async function listAuditLogs(params?: {
    page?: number;
    page_size?: number;
    action?: string;
    user_id?: string;
    resource_type?: string;
    workspace_id?: string;
}): Promise<AuditLogListResponse> {
    const qs = new URLSearchParams();
    if (params?.page) qs.set("page", String(params.page));
    if (params?.page_size) qs.set("page_size", String(params.page_size));
    if (params?.action) qs.set("action", params.action);
    if (params?.user_id) qs.set("user_id", params.user_id);
    if (params?.resource_type) qs.set("resource_type", params.resource_type);
    if (params?.workspace_id) qs.set("workspace_id", params.workspace_id);
    return apiFetch(`/admin/audit-logs?${qs.toString()}`);
}

export async function exportAuditLogs(
    format: "ndjson" | "csv",
    filters?: {
        action?: string;
        user_id?: string;
        resource_type?: string;
        workspace_id?: string;
    },
): Promise<Blob> {
    const qs = new URLSearchParams({ format });
    if (filters?.action) qs.set("action", filters.action);
    if (filters?.user_id) qs.set("user_id", filters.user_id);
    if (filters?.resource_type) qs.set("resource_type", filters.resource_type);
    if (filters?.workspace_id) qs.set("workspace_id", filters.workspace_id);
    const response = await fetch(`${API_BASE}/admin/audit-logs/export?${qs.toString()}`, {
        credentials: "include",
    });
    if (!response.ok) {
        throw new Error("Failed to export audit logs");
    }
    return response.blob();
}

export type IdentityProvider = {
    id: string;
    slug: string;
    name: string;
    provider_type: string;
    issuer: string;
    client_id: string;
    scopes: string[];
    domain_allowlist: string[];
    enabled: boolean;
    enforce_sso: boolean;
    has_client_secret: boolean;
    created_at: string;
    updated_at: string;
};

export async function listIdentityProviders(): Promise<IdentityProvider[]> {
    return apiFetch("/admin/identity-providers");
}

export async function createIdentityProvider(payload: Record<string, unknown>): Promise<IdentityProvider> {
    return apiFetch("/admin/identity-providers", {
        method: "POST",
        body: JSON.stringify(payload),
    });
}

export async function updateIdentityProvider(
    providerId: string,
    payload: Record<string, unknown>,
): Promise<IdentityProvider> {
    return apiFetch(`/admin/identity-providers/${providerId}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
    });
}

export async function testIdentityProvider(providerId: string): Promise<Record<string, unknown>> {
    return apiFetch(`/admin/identity-providers/${providerId}/test`, { method: "POST" });
}
