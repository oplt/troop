#!/usr/bin/env node
const fs = require('fs');

const [graphPath, layersPath, tourPath, scanPath, outputPath, commitHash, analyzedAt] = process.argv.slice(2);
const graph = JSON.parse(fs.readFileSync(graphPath, 'utf8'));
const scan = JSON.parse(fs.readFileSync(scanPath, 'utf8'));
let layersRaw = JSON.parse(fs.readFileSync(layersPath, 'utf8'));
let tourRaw = JSON.parse(fs.readFileSync(tourPath, 'utf8'));

const nodes = Array.isArray(graph.nodes) ? graph.nodes : [];
const edges = Array.isArray(graph.edges) ? graph.edges : [];
const nodeIds = new Set(nodes.map((node) => node.id));
const knownPrefixes = /^(file|config|document|service|pipeline|table|schema|resource|endpoint):/;
const asNodeId = (value) => {
  if (value && typeof value === 'object') value = value.id;
  if (typeof value !== 'string') return null;
  return knownPrefixes.test(value) ? value : `file:${value}`;
};
const kebab = (value) => String(value || 'unnamed')
  .trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');

if (!Array.isArray(layersRaw)) layersRaw = Array.isArray(layersRaw.layers) ? layersRaw.layers : [];
const layers = layersRaw.map((layer) => {
  const sourceIds = Array.isArray(layer.nodeIds) ? layer.nodeIds : (Array.isArray(layer.nodes) ? layer.nodes : []);
  return {
    id: layer.id || `layer:${kebab(layer.name)}`,
    name: layer.name || 'Unnamed Layer',
    description: layer.description || 'No description available',
    nodeIds: [...new Set(sourceIds.map(asNodeId).filter((id) => id && nodeIds.has(id)))],
  };
}).filter((layer) => layer.nodeIds.length > 0);

if (!Array.isArray(tourRaw)) tourRaw = Array.isArray(tourRaw.steps) ? tourRaw.steps : [];
const tour = tourRaw.map((step, index) => {
  const sourceIds = Array.isArray(step.nodeIds) ? step.nodeIds : (Array.isArray(step.nodesToInspect) ? step.nodesToInspect : []);
  const normalized = {
    order: Number.isInteger(step.order) ? step.order : index + 1,
    title: step.title || `Step ${index + 1}`,
    description: step.description || step.whyItMatters || 'No description available',
    nodeIds: [...new Set(sourceIds.map(asNodeId).filter((id) => id && nodeIds.has(id)))],
  };
  if (typeof step.languageLesson === 'string' && step.languageLesson.trim()) {
    normalized.languageLesson = step.languageLesson;
  }
  return normalized;
}).filter((step) => step.nodeIds.length > 0)
  .sort((a, b) => a.order - b.order)
  .map((step, index) => ({ ...step, order: index + 1 }));

const finalGraph = {
  version: '1.0.0',
  project: {
    name: scan.name || 'troop',
    languages: Array.isArray(scan.languages) ? scan.languages : [],
    frameworks: Array.isArray(scan.frameworks) ? scan.frameworks : [],
    description: scan.description || 'No description available',
    analyzedAt,
    gitCommitHash: commitHash,
  },
  nodes,
  edges,
  layers,
  tour,
};

fs.writeFileSync(outputPath, `${JSON.stringify(finalGraph, null, 2)}\n`);

