import { Chip, Stack, Typography } from "@mui/material";

import type { SemanticMemoryEntry } from "../../api/orchestration";
import { formatDateTime } from "../../utils/formatters";

function text(value: unknown): string | null {
    if (typeof value === "string" && value.trim()) return value;
    if (typeof value === "number") return String(value);
    return null;
}

export function SemanticMemoryProvenanceDetails({
    entry,
    compact = false,
}: {
    entry: SemanticMemoryEntry;
    compact?: boolean;
}) {
    const provenance = entry.provenance ?? {};
    const extras =
        provenance.extras && typeof provenance.extras === "object"
            ? (provenance.extras as Record<string, unknown>)
            : {};
    const source = text(provenance.source) ?? "api";
    const creator =
        entry.created_by_user_id ?? text(provenance.created_by_user_id) ?? text(provenance.source_agent_id);
    const task = entry.source_task_id ?? text(provenance.source_task_id) ?? text(extras.task_id);
    const run = entry.source_run_id ?? text(provenance.source_run_id) ?? text(extras.run_id);
    const document =
        text(entry.metadata.source_document_id) ??
        text(entry.metadata.document_id) ??
        entry.source_chunk_id ??
        text(extras.document_id);
    const confidence = Number.isFinite(entry.confidence) ? `${Math.round(entry.confidence * 100)}%` : "—";
    const status = entry.status || "current";

    if (compact) {
        return (
            <Stack direction="row" spacing={0.75} useFlexGap flexWrap="wrap" sx={{ mt: 0.75 }}>
                <Chip size="small" label={status} color={status === "current" ? "success" : "default"} />
                <Chip size="small" variant="outlined" label={`${source} · ${confidence}`} />
                {task ? <Chip size="small" variant="outlined" label={`Task ${task.slice(0, 8)}`} /> : null}
                {run ? <Chip size="small" variant="outlined" label={`Run ${run.slice(0, 8)}`} /> : null}
                {document ? <Chip size="small" variant="outlined" label={`Doc ${document.slice(0, 8)}`} /> : null}
            </Stack>
        );
    }

    const rows = [
        ["Source", source],
        ["Created by", creator ?? "System"],
        ["Task", task ?? "—"],
        ["Run", run ?? "—"],
        ["Document / chunk", document ?? "—"],
        ["Valid from", formatDateTime(entry.valid_from || entry.created_at)],
        ["Valid until", entry.valid_until ? formatDateTime(entry.valid_until) : "Current"],
        ["Confidence", confidence],
        ["Status", status],
        ["Version", String(entry.memory_version || 1)],
        ["Canonical key", entry.canonical_key ?? "—"],
        ["Supersedes", entry.supersedes_memory_id ?? "—"],
    ] as const;

    return (
        <Stack spacing={0.75}>
            {rows.map(([label, value]) => (
                <Stack key={label} direction={{ xs: "column", sm: "row" }} spacing={0.5}>
                    <Typography variant="caption" color="text.secondary" sx={{ minWidth: 132 }}>
                        {label}
                    </Typography>
                    <Typography variant="body2" sx={{ overflowWrap: "anywhere" }}>
                        {value}
                    </Typography>
                </Stack>
            ))}
        </Stack>
    );
}
