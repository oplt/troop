import { defineConfig, devices } from "@playwright/test";

const isCi = Boolean(process.env.CI);

export default defineConfig({
    testDir: "./e2e",
    fullyParallel: false,
    workers: 1,
    retries: isCi ? 2 : 0,
    timeout: 120_000,
    reporter: isCi ? [["github"], ["html", { open: "never" }]] : "html",
    globalSetup: "./e2e/global-setup.ts",
    use: {
        baseURL: process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:5173",
        trace: "on-first-retry",
        screenshot: "only-on-failure",
        video: "retain-on-failure",
    },
    projects: isCi
        ? [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }]
        : [
              { name: "chromium", use: { ...devices["Desktop Chrome"] } },
              { name: "firefox", use: { ...devices["Desktop Firefox"] } },
          ],
    webServer: [
        {
            command:
                'bash -lc "cd .. && PYTHONPATH=. python -m uvicorn backend.api.main:app --host 127.0.0.1 --port 8000"',
            url: "http://127.0.0.1:8000/health/live",
            reuseExistingServer: !isCi,
            timeout: 120_000,
            env: {
                ...process.env,
                PYTHONPATH: "..",
                APP_ENV: "dev",
                CELERY_TASK_ALWAYS_EAGER: "true",
                JWT_SECRET: process.env.JWT_SECRET ?? "ci-only-secret-not-for-production",
                SECRETS_ENCRYPTION_KEY:
                    process.env.SECRETS_ENCRYPTION_KEY ??
                    "eUL60QMh9TqTrgJy-50f2CWp2yhh50lTM5Z-Q-BOY1A=",
            },
        },
        {
            command: "pnpm run dev --host 127.0.0.1 --port 5173",
            url: "http://127.0.0.1:5173",
            reuseExistingServer: !isCi,
            timeout: 120_000,
        },
    ],
});
