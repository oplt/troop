#!/usr/bin/env node
const fs = require('fs');

const [assembledPath, scanPath, finalPath, fingerprintInputPath] = process.argv.slice(2);
const graph = JSON.parse(fs.readFileSync(assembledPath, 'utf8'));
const scan = JSON.parse(fs.readFileSync(scanPath, 'utf8'));

fs.writeFileSync(finalPath, `${JSON.stringify(graph, null, 2)}\n`);
fs.writeFileSync(fingerprintInputPath, `${JSON.stringify({
  projectRoot: process.cwd(),
  sourceFilePaths: (scan.files || []).map((file) => file.path),
  gitCommitHash: graph.project.gitCommitHash,
}, null, 2)}\n`);

