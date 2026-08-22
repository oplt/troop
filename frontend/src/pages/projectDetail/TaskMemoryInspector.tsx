import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Divider, Link, Paper, Stack, TextField, Typography } from "@mui/material";
import { Link as RouterLink, useNavigate } from "react-router-dom";
import {
    getRunWorkingMemory,
    getTaskMemoryCoordination,
    listSemanticMemory,
    patchTaskMemoryCoordination,
    searchEpisodicMemory,
} from "../../api/orchestration";
import { useSnackbar } from "../../app/snackbarContext";
import { queryKeys } from "../../config/queryKeys";
import { formatDateTime } from "../../utils/formatters";
import { extractApiErrorMessage } from "../../utils/apiErrors";
import { SemanticMemoryProvenanceDetails } from "../../features/memory/SemanticMemoryProvenanceDetails";

export function TaskMemoryInspector({
    projectId,
    taskId,
    lastRunId,
}: {
    projectId: string;
    taskId: string;
    lastRunId?: string;
}) {
    const navigate = useNavigate();
    const queryClient = useQueryClient();
    const { showToast } = useSnackbar();
    const [sharedDraft, setSharedDraft] = useState("");
    const [privateJsonDraft, setPrivateJsonDraft] = useState("{}");

    const { data: episodic } = useQuery({
        queryKey: queryKeys.orchestration.taskEpisodic(projectId, taskId),
        queryFn: () => searchEpisodicMemory(projectId, { task_id: taskId, limit: 40 }),
        enabled: Boolean(projectId && taskId),
    });
    const { data: semanticRows = [] } = useQuery({
        queryKey: queryKeys.orchestration.taskSemantic(projectId, taskId),
        queryFn: () => listSemanticMemory(projectId, { source_task_id: taskId, limit: 50 }),
        enabled: Boolean(projectId && taskId),
    });
    const { data: coord } = useQuery({
        queryKey: queryKeys.orchestration.taskCoord(projectId, taskId),
        queryFn: () => getTaskMemoryCoordination(projectId, taskId),
        enabled: Boolean(projectId && taskId),
    });
    const { data: wm } = useQuery({
        queryKey: queryKeys.orchestration.runWorkingMemory(lastRunId || ""),
        queryFn: () => getRunWorkingMemory(lastRunId!),
        enabled: Boolean(lastRunId),
    });

    useEffect(() => {
        if (!coord) return;
        // eslint-disable-next-line react-hooks/set-state-in-effect
        setSharedDraft(coord.shared ?? "");
        try {
            setPrivateJsonDraft(JSON.stringify(coord.private ?? {}, null, 2));
        } catch {
            setPrivateJsonDraft("{}");
        }
    }, [coord]);

    const patchCoordMut = useMutation({
        mutationFn: async () => {
            let priv: Record<string, string> = {};
            try {
                const parsed = JSON.parse(privateJsonDraft) as unknown;
                if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
                    priv = Object.fromEntries(
                        Object.entries(parsed as Record<string, unknown>).map(([k, v]) => [k, String(v)]),
                    );
                }
            } catch {
                throw new Error("INVALID_JSON");
            }
            return patchTaskMemoryCoordination(projectId, taskId, { shared: sharedDraft, private: priv });
        },
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.taskCoord(projectId, taskId) });
            showToast({ message: "Task memory coordination saved.", severity: "success" });
        },
        onError: (error: unknown) => {
            const msg =
                error instanceof Error && error.message === "INVALID_JSON"
                    ? "Private scratchpad JSON is invalid."
                    : extractApiErrorMessage(error, "Could not save coordination.");
            showToast({ message: msg, severity: "error" });
        },
    });

    const hits = episodic?.hits ?? [];

    return (
        <Stack spacing={1.25} sx={{ mt: 1 }}>
            <Typography variant="subtitle2">Task memory</Typography>
            <Typography variant="caption" color="text.secondary">
                Working snapshot from the latest run (if any). Blackboard = shared coordination; private JSON = per-agent
                scratchpad keys.
            </Typography>
            {lastRunId ? (
                <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                    <Button size="small" variant="outlined" onClick={() => navigate(`/runs/${lastRunId}`)}>
                        Open run {lastRunId.slice(0, 8)}…
                    </Button>
                    <Typography variant="caption" color="text.secondary">
                        Updated {wm ? formatDateTime(wm.updated_at) : "…"}
                    </Typography>
                </Stack>
            ) : (
                <Typography variant="caption" color="text.secondary">
                    No run yet — start a run to populate working memory.
                </Typography>
            )}
            {wm ? (
                <Paper variant="outlined" sx={{ p: 1, borderRadius: 1, maxHeight: 160, overflow: "auto" }}>
                    <Typography variant="caption" component="pre" sx={{ whiteSpace: "pre-wrap", wordBreak: "break-word", m: 0 }}>
                        {JSON.stringify(
                            {
                                objective: wm.objective,
                                accepted_plan: wm.accepted_plan,
                                latest_findings: wm.latest_findings,
                                temp_notes: wm.temp_notes,
                                open_questions: wm.open_questions,
                            },
                            null,
                            2,
                        )}
                    </Typography>
                </Paper>
            ) : null}
            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.5 }}>
                Blackboard (shared)
            </Typography>
            <TextField
                size="small"
                multiline
                minRows={2}
                value={sharedDraft}
                onChange={(e) => setSharedDraft(e.target.value)}
                fullWidth
                placeholder="Visible to all agents on this task…"
            />
            <Typography variant="caption" color="text.secondary">
                Private scratchpad (JSON object: agent_id → text)
            </Typography>
            <TextField
                size="small"
                multiline
                minRows={3}
                value={privateJsonDraft}
                onChange={(e) => setPrivateJsonDraft(e.target.value)}
                fullWidth
            />
            <Button size="small" variant="contained" disabled={patchCoordMut.isPending} onClick={() => patchCoordMut.mutate()}>
                Save blackboard / scratchpad
            </Button>
            <Divider sx={{ my: 0.5 }} />
            <Typography variant="caption" color="text.secondary">
                Episodic timeline (indexed rows for this task)
            </Typography>
            <Stack spacing={0.5} sx={{ maxHeight: 180, overflow: "auto" }}>
                {hits.length === 0 ? (
                    <Typography variant="caption" color="text.secondary">
                        No episodic hits yet.
                    </Typography>
                ) : (
                    hits.slice(0, 20).map((hit, i) => (
                        <Paper key={`${String(hit.kind)}-${String(hit.id)}-${i}`} variant="outlined" sx={{ p: 0.75, borderRadius: 1 }}>
                            <Typography variant="caption" color="text.secondary">
                                {String(hit.kind)} · {formatDateTime(String(hit.created_at))}
                            </Typography>
                            <Typography variant="caption" sx={{ display: "block", whiteSpace: "pre-wrap" }}>
                                {String(hit.snippet ?? "").slice(0, 280)}
                            </Typography>
                        </Paper>
                    ))
                )}
            </Stack>
            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.5 }}>
                Promoted semantic entries (source_task_id)
            </Typography>
            <Stack spacing={0.5} sx={{ maxHeight: 140, overflow: "auto" }}>
                {semanticRows.length === 0 ? (
                    <Typography variant="caption" color="text.secondary">
                        None linked to this task.
                    </Typography>
                ) : (
                    semanticRows.map((row) => (
                        <Paper key={row.id} variant="outlined" sx={{ p: 0.75, borderRadius: 1 }}>
                            <Typography variant="caption" sx={{ display: "block" }}>
                                <Link component={RouterLink} to={`/projects/${projectId}/memory`} underline="hover">
                                    [{row.entry_type}]
                                </Link>{" "}
                                {row.title}
                            </Typography>
                            <SemanticMemoryProvenanceDetails entry={row} compact />
                        </Paper>
                    ))
                )}
            </Stack>
        </Stack>
    );
}
