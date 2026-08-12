#!/usr/bin/env node
const fs = require('fs');

const [graphPath, scanPath, metaPath] = process.argv.slice(2);
const graph = JSON.parse(fs.readFileSync(graphPath, 'utf8'));
const scan = JSON.parse(fs.readFileSync(scanPath, 'utf8'));
fs.writeFileSync(metaPath, `${JSON.stringify({
  lastAnalyzedAt: graph.project.analyzedAt,
  gitCommitHash: graph.project.gitCommitHash,
  version: graph.version,
  analyzedFiles: scan.totalFiles,
}, null, 2)}\n`);
