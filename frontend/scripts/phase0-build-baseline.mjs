#!/usr/bin/env node

/**
 * Report a repeatable frontend build-size baseline after `pnpm build`.
 *
 * Usage:
 *   pnpm run build
 *   pnpm run baseline:build -- --output ../artifacts/frontend-baseline.json
 */

import { readdir, stat, writeFile } from "node:fs/promises";
import { join, relative, resolve } from "node:path";

const root = resolve(process.cwd(), "dist");
const outputFlag = process.argv.indexOf("--output");
const output = outputFlag >= 0 ? process.argv[outputFlag + 1] : null;

async function filesUnder(directory) {
    const entries = await readdir(directory, { withFileTypes: true });
    const files = [];
    for (const entry of entries) {
        const path = join(directory, entry.name);
        if (entry.isDirectory()) files.push(...(await filesUnder(path)));
        else files.push(path);
    }
    return files;
}

function formatBytes(bytes) {
    return Math.round(bytes / 1024);
}

const files = await filesUnder(root);
const assets = [];
for (const file of files) {
    const size = (await stat(file)).size;
    const path = relative(root, file);
    assets.push({ path, bytes: size, kibibytes: formatBytes(size) });
}
assets.sort((left, right) => right.bytes - left.bytes);

const summary = {
    schema_version: 1,
    captured_at: new Date().toISOString(),
    dist: "frontend/dist",
    file_count: assets.length,
    total_bytes: assets.reduce((total, asset) => total + asset.bytes, 0),
    total_kibibytes: formatBytes(assets.reduce((total, asset) => total + asset.bytes, 0)),
    javascript_bytes: assets
        .filter((asset) => asset.path.endsWith(".js"))
        .reduce((total, asset) => total + asset.bytes, 0),
    css_bytes: assets
        .filter((asset) => asset.path.endsWith(".css"))
        .reduce((total, asset) => total + asset.bytes, 0),
    largest_assets: assets.slice(0, 20),
};

const payload = `${JSON.stringify(summary, null, 2)}\n`;
if (output) {
    await writeFile(resolve(process.cwd(), output), payload, "utf8");
}
process.stdout.write(payload);
