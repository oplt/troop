export const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000/api/v1";

let refreshPromise: Promise<boolean> | null = null;

export function readCookie(name: string): string | null {
    const match = document.cookie.match(
        new RegExp(`(?:^|; )${name.replace(/[.*+?^${}()|[\\]\\\\]/g, "\\$&")}=([^;]*)`)
    );
    return match ? decodeURIComponent(match[1]) : null;
}

async function refreshAccessToken(): Promise<boolean> {
    try {
        const res = await fetch(`${API_BASE}/auth/refresh`, {
            method: "POST",
            credentials: "include",
            headers: buildCsrfHeaders(),
        });
        return res.ok;
    } catch {
        return false;
    }
}

function buildCsrfHeaders(): HeadersInit {
    const csrfToken = readCookie("csrf_token");
    return csrfToken ? { "X-CSRF-Token": csrfToken } : {};
}

export async function apiFetch<T>(
    path: string,
    options: RequestInit = {},
    retry = true
): Promise<T> {
    const headers = new Headers(options.headers ?? {});
    const isFormData = options.body instanceof FormData;

    if (!isFormData && options.body !== undefined && !headers.has("Content-Type")) {
        headers.set("Content-Type", "application/json");
    }
    if (!headers.has("X-CSRF-Token")) {
        const csrfValue = readCookie("csrf_token");
        if (csrfValue) {
            headers.set("X-CSRF-Token", csrfValue);
        }
    }

    const response = await fetch(`${API_BASE}${path}`, {
        ...options,
        headers,
        credentials: "include",
    });

    if (response.status === 401 && retry) {
        // Deduplicate concurrent refresh attempts
        if (!refreshPromise) {
            refreshPromise = refreshAccessToken().finally(() => {
                refreshPromise = null;
            });
        }
        const refreshed = await refreshPromise;
        if (!refreshed) {
            throw new Error("Session expired. Please sign in again.");
        }
        return apiFetch<T>(path, options, false);
    }

    if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: "Request failed" })) as {
            detail?: unknown;
            errors?: unknown;
            warnings?: unknown;
        };
        const detail = error.detail;
        if (typeof detail === "string" && detail.trim()) {
            throw new Error(detail);
        }
        if (detail && typeof detail === "object") {
            const nested = detail as {
                errors?: unknown;
                warnings?: unknown;
                message?: unknown;
                checks?: unknown;
            };
            const nestedErrors = Array.isArray(nested.errors) ? nested.errors.filter((item): item is string => typeof item === "string") : [];
            const nestedWarnings = Array.isArray(nested.warnings) ? nested.warnings.filter((item): item is string => typeof item === "string") : [];
            const nestedMessage = typeof nested.message === "string" ? nested.message.trim() : "";
            const checkDetails: string[] = [];
            if (Array.isArray(nested.checks)) {
                for (const row of nested.checks) {
                    if (typeof row !== "object" || !row || (row as { passed?: boolean }).passed !== false) continue;
                    const line = (row as { detail?: unknown }).detail;
                    if (typeof line === "string" && line.trim()) checkDetails.push(line.trim());
                }
            }
            const parts = [nestedMessage, ...nestedErrors, ...nestedWarnings, ...checkDetails].filter(Boolean);
            if (parts.length > 0) {
                throw new Error(parts.join(" — "));
            }
            throw new Error(JSON.stringify(detail));
        }
        throw new Error("Request failed");
    }

    // Handle 204 No Content
    if (response.status === 204) return undefined as T;

    return response.json();
}
