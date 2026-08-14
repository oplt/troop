import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

export type E2ECredentials = {
    email: string;
    password: string;
    userId: string;
};

const credentialsPath = path.join(
    path.dirname(fileURLToPath(import.meta.url)),
    "../.auth/credentials.json",
);

export function readCredentials(): E2ECredentials {
    const raw = fs.readFileSync(credentialsPath, "utf8");
    return JSON.parse(raw) as E2ECredentials;
}
