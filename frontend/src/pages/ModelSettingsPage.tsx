import { Alert, Stack, Typography } from "@mui/material";
import { useQuery } from "@tanstack/react-query";
import { getOrchestrationRuntimeInfo } from "../api/orchestration";
import { PageHeader } from "../components/ui/PageHeader";
import { PageShell } from "../components/ui/PageShell";
import { SectionCard } from "../components/ui/SectionCard";
import { ProviderSettingsPanel } from "./OrchestrationSettingsPage";

export default function ModelSettingsPage() {
    const { data: runtime } = useQuery({
        queryKey: ["orchestration", "runtime-info"],
        queryFn: getOrchestrationRuntimeInfo,
    });

    return (
        <PageShell maxWidth="xl">
            <PageHeader
                eyebrow="Orchestration"
                title="Model settings"
                description="Central place for provider credentials, health checks, model comparison, and deployment flags that affect routing."
                meta={
                    runtime ? (
                        <Typography variant="body2" color="text.secondary">
                            Offline: {runtime.orchestration_offline_mode ? "on" : "off"} · Failover:{" "}
                            {runtime.orchestration_provider_failover ? "on" : "off"} · LangGraph router:{" "}
                            {runtime.orchestration_use_langgraph ? "on" : "off"} · Durable queue:{" "}
                            {runtime.orchestration_durable_queue_backend}
                        </Typography>
                    ) : null
                }
            />

            {runtime?.orchestration_offline_mode && (
                <Alert severity="warning" sx={{ mb: 2 }}>
                    Orchestration offline mode is enabled on the server. All LLM calls use the local heuristic provider
                    only.
                </Alert>
            )}
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
                        Offline mode forces air-gapped / local-only execution. Provider failover walks additional enabled
                        providers when models fail on the primary host. LangGraph toggles the in-process graph router;
                        durable queue backend is reported for future Temporal wiring.
                    </Typography>
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
