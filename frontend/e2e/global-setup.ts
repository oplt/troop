import { execSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, "../..");
const authDir = path.join(__dirname, ".auth");
const credentialsPath = path.join(authDir, "credentials.json");
const pythonBin =
    process.env.E2E_PYTHON ??
    (fs.existsSync(path.join(repoRoot, "backend/.venv/bin/python"))
        ? path.join(repoRoot, "backend/.venv/bin/python")
        : "python");

export default async function globalSetup() {
    fs.mkdirSync(authDir, { recursive: true });
    execSync(
        [
            pythonBin,
            "backend/scripts/seed_playwright_e2e.py",
            "credentials",
            "--output",
            credentialsPath,
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
}
