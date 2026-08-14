import { Paper, Stack, Typography } from "@mui/material";

import type { AgentVersion } from "../../../api/orchestration";

type AgentVersionHistoryProps = {
    versions: AgentVersion[];
};

export function AgentVersionHistory({ versions }: AgentVersionHistoryProps) {
    return (
        <Stack spacing={1.5}>
            {versions.map((version) => (
                <Paper key={version.id} variant="outlined" sx={{ p: 1.5 }}>
                    <Stack direction="row" justifyContent="space-between">
                        <Typography variant="subtitle2">Version {version.version_number}</Typography>
                        <Typography variant="caption" color="text.secondary">
                            {new Date(version.created_at).toLocaleString()}
                        </Typography>
                    </Stack>
                    <Typography variant="caption" color="text.secondary">
                        {version.source_markdown
                            ? `${version.source_markdown.slice(0, 180)}${version.source_markdown.length > 180 ? "…" : ""}`
                            : "Structured contract snapshot"}
                    </Typography>
                </Paper>
            ))}
            {versions.length === 0 && (
                <Typography color="text.secondary">Save the first contract version to begin history.</Typography>
            )}
        </Stack>
    );
}
