import { Alert, Box, Chip, Stack, Typography } from "@mui/material";
import { useQuery } from "@tanstack/react-query";
import { getOrchestrationRuntimeInfo } from "../api/orchestration";
import { PageShell } from "../components/ui/PageShell";
import { SectionCard } from "../components/ui/SectionCard";
import { ProviderSettingsPanel } from "./ProviderSettingsPanel";

export default function ModelSettingsPage() {
    const { data: runtime } = useQuery({
        queryKey: ["orchestration", "runtime-info"],
        queryFn: getOrchestrationRuntimeInfo,
    });

    return (
        <PageShell maxWidth="xl">

            {runtime?.orchestration_use_langgraph && (
                <Alert severity="info" sx={{ mb: 2 }}>
                    LangGraph routing is enabled: run modes are dispatched through a LangGraph StateGraph inside the worker
                    while Celery still enqueues runs.
                </Alert>
            )}

            <Stack spacing={2}>
                <SectionCard
                    title="Runtime flags"
                    description="Values come from server environment (see backend/.env.example). Change them in backend .env and restart the API."
                >
                    <Typography variant="body2" color="text.secondary">
                        Provider failover walks additional enabled providers when models fail on the primary host. LangGraph
                        routes supervisor/worker run modes inside the execution worker; Celery and Redis provide at-least-once
                        delivery while Postgres checkpoints preserve resumable workflow state.
                    </Typography>
                    {runtime?.durable_backend && (
                        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mt: 1.5 }}>
                            <Chip size="small" color={runtime.durable_backend.available ? "success" : "error"} label={`Durable: ${String(runtime.durable_backend.active ?? runtime.durable_backend.configured ?? "unknown")}`} />
                            <Chip size="small" variant="outlined" label={runtime.durable_backend.delivery ? String(runtime.durable_backend.delivery) : "unavailable"} />
                            <Chip size="small" variant="outlined" label={runtime.durable_backend.checkpointed ? "Postgres checkpointed" : "not checkpointed"} />
                            <Chip size="small" variant="outlined" label={runtime.realtime_transport?.protocol ? `Realtime: ${String(runtime.realtime_transport.protocol)}` : "Realtime unavailable"} />
                        </Stack>
                    )}
                    {runtime?.execution_topology && (
                        <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "repeat(2, minmax(0, 1fr))" }, gap: 1, mt: 1.5 }}>
                            {Object.entries(runtime.execution_topology).map(([key, value]) => (
                                <Typography key={key} variant="caption" color="text.secondary">
                                    <strong>{key.replaceAll("_", " ")}</strong>: {String(value)}
                                </Typography>
                            ))}
                        </Box>
                    )}
                    {runtime?.celery_queues && Object.keys(runtime.celery_queues).length > 0 && (
                        <Typography variant="caption" component="div" sx={{ mt: 1.5, fontFamily: "IBM Plex Mono, monospace" }}>
                            Celery queues:{" "}
                            {Object.entries(runtime.celery_queues)
                                .map(([k, v]) => `${k}=${v}`)
                                .join(" · ")}
                        </Typography>
                    )}
                </SectionCard>
                <ProviderSettingsPanel />
            </Stack>
        </PageShell>
    );
}
