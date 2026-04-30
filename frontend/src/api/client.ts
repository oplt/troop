function defaultApiBase() {
    if (typeof window === "undefined") return "http://localhost:8000/api/v1";
    return `${window.location.protocol}//${window.location.hostname}:8000/api/v1`;
}

export const API_BASE = import.meta.env.VITE_API_BASE ?? defaultApiBase();

let refreshPromise: Promise<boolean> | null = null;
let authStateVersion = 0;
const AUTH_EXPIRED_EVENT = "troop:auth-expired";

export class SessionExpiredError extends Error {
    constructor() {
        super("Session expired. Please sign in again.");
        this.name = "SessionExpiredError";
    }
}

export function markAuthStateChanged() {
    authStateVersion += 1;
}

function notifyAuthExpired(observedAuthStateVersion: number) {
    if (observedAuthStateVersion !== authStateVersion) return;
    window.dispatchEvent(new CustomEvent(AUTH_EXPIRED_EVENT));
}

export function onAuthExpired(listener: () => void): () => void {
    window.addEventListener(AUTH_EXPIRED_EVENT, listener);
    return () => window.removeEventListener(AUTH_EXPIRED_EVENT, listener);
}

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

function shouldRefreshOnUnauthorized(path: string): boolean {
    if (path === "/auth/me") return true;
    return !path.startsWith("/auth/");
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

    if (response.status === 401 && retry && shouldRefreshOnUnauthorized(path)) {
        const observedAuthStateVersion = authStateVersion;
        // Deduplicate concurrent refresh attempts
        if (!refreshPromise) {
            refreshPromise = refreshAccessToken().finally(() => {
                refreshPromise = null;
            });
        }
        const refreshed = await refreshPromise;
        if (!refreshed) {
            notifyAuthExpired(observedAuthStateVersion);
            throw new SessionExpiredError();
        }
        return apiFetch<T>(path, options, false);
    }

    if (response.status === 401 && !retry && shouldRefreshOnUnauthorized(path)) {
        notifyAuthExpired(authStateVersion);
        throw new SessionExpiredError();
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
