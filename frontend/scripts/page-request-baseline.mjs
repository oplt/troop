#!/usr/bin/env node

import { writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { chromium } from "@playwright/test";

function option(name, fallback = null) {
    const index = process.argv.indexOf(name);
    return index >= 0 ? process.argv[index + 1] : fallback;
}

const baseUrl = option("--base-url", "http://127.0.0.1:5173");
const output = option("--output");
const storageState = option("--storage-state");
const routes = process.argv
    .flatMap((value, index, values) => (value === "--route" ? [values[index + 1]] : []))
    .filter(Boolean);
const targets = routes.length ? routes : ["/dashboard", "/projects", "/ai"];

const browser = await chromium.launch();
const context = await browser.newContext(storageState ? { storageState } : {});
const page = await context.newPage();
const results = [];

for (const route of targets) {
    const requests = [];
    const listener = (request) => {
        if (request.url().includes("/api/v1/")) {
            requests.push({ method: request.method(), url: request.url().split("?", 1)[0] });
        }
    };
    page.on("request", listener);
    const started = performance.now();
    let error = null;
    try {
        await page.goto(new URL(route, baseUrl).toString(), { waitUntil: "networkidle" });
    } catch (caught) {
        error = caught instanceof Error ? caught.message : String(caught);
    }
    page.off("request", listener);
    results.push({
        route,
        elapsed_ms: Math.round(performance.now() - started),
        request_count: requests.length,
        unique_request_count: new Set(requests.map((item) => `${item.method} ${item.url}`)).size,
        requests,
        error,
    });
}

await browser.close();
const report = {
    schema_version: 1,
    captured_at: new Date().toISOString(),
    base_url: baseUrl,
    results,
};
const payload = `${JSON.stringify(report, null, 2)}\n`;
if (output) await writeFile(resolve(process.cwd(), output), payload, "utf8");
process.stdout.write(payload);
