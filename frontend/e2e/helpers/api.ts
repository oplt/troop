import { execSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import type { APIRequestContext } from "@playwright/test";

const API_BASE = process.env.E2E_API_BASE ?? "http://localhost:8000/api/v1";
const CSRF_COOKIE = process.env.E2E_CSRF_COOKIE ?? "csrf_token";
const CSRF_HEADER = process.env.E2E_CSRF_HEADER ?? "X-CSRF-Token";

export type ApiSession = {
    request: APIRequestContext;
    csrfToken: string;
};

export async function apiSignIn(
    request: APIRequestContext,
    email: string,
    password: string,
): Promise<ApiSession> {
    const response = await request.post(`${API_BASE}/auth/sign-in`, {
        data: { email, password },
    });
    if (!response.ok()) {
        throw new Error(`Sign-in failed (${response.status()}): ${await response.text()}`);
    }
    const cookies = await request.storageState();
    const csrfToken =
        cookies.cookies.find((cookie) => cookie.name === CSRF_COOKIE)?.value ?? "";
    if (!csrfToken) {
        throw new Error("Missing CSRF cookie after sign-in");
    }
    return { request, csrfToken };
}

export async function apiFetch<T = unknown>(
    session: ApiSession,
    route: string,
    init: { method?: string; data?: unknown } = {},
): Promise<T> {
    const response = await session.request.fetch(`${API_BASE}${route}`, {
        method: init.method ?? "GET",
        headers: {
            "Content-Type": "application/json",
            [CSRF_HEADER]: session.csrfToken,
        },
        data: init.data,
    });
    const text = await response.text();
    if (!response.ok()) {
        throw new Error(`${init.method ?? "GET"} ${route} failed (${response.status()}): ${text}`);
    }
    return text ? (JSON.parse(text) as T) : ({} as T);
}

export function seedFixture(
    mode: "stale-approval" | "email-approval" | "reauth-connector" | "critical-flow",
    userId: string,
): Record<string, unknown> {
    const repoRoot = path.resolve(import.meta.dirname, "../../..");
    const pythonBin =
        process.env.E2E_PYTHON ??
        (fs.existsSync(path.join(repoRoot, "backend/.venv/bin/python"))
            ? path.join(repoRoot, "backend/.venv/bin/python")
            : "python");
    const output = path.join(os.tmpdir(), `troop-e2e-${mode}-${userId}.json`);
    execSync(
        [
            pythonBin,
            "backend/scripts/seed_playwright_e2e.py",
            mode,
            "--user-id",
            userId,
            "--output",
            output,
        ].join(" "),
        {
            cwd: repoRoot,
            env: {
                ...process.env,
                PYTHONPATH: repoRoot,
                APP_ENV: process.env.APP_ENV ?? "dev",
                JWT_SECRET: process.env.JWT_SECRET ?? "ci-only-secret-not-for-production",
                SECRETS_ENCRYPTION_KEY:
                    process.env.SECRETS_ENCRYPTION_KEY ??
                    "eUL60QMh9TqTrgJy-50f2CWp2yhh50lTM5Z-Q-BOY1A=",
            },
            stdio: "inherit",
        },
    );
    return JSON.parse(fs.readFileSync(output, "utf8")) as Record<string, unknown>;
}
