import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Box, Button, Chip, CircularProgress, Stack, TextField, Typography } from "@mui/material";
import { CallSplit as DecomposeIcon } from "@mui/icons-material";
import { decomposeTask, listSubtasks } from "../../../../api/orchestration";
import { useSnackbar } from "../../../../app/snackbarContext";
import { queryKeys } from "../../../../config/queryKeys";
import { extractApiErrorMessage } from "../../../../utils/apiErrors";

export function SubtaskPanel({ projectId, taskId, taskTitle }: { projectId: string; taskId: string; taskTitle: string }) {
    const queryClient = useQueryClient();
    const { showToast } = useSnackbar();
    const [maxSubtasks, setMaxSubtasks] = useState("4");
    const [context, setContext] = useState("");
    const { data: subtasks = [], isLoading } = useQuery({
        queryKey: queryKeys.orchestration.subtasks(taskId),
        queryFn: () => listSubtasks(projectId, taskId),
    });
    const decomposeMutation = useMutation({
        mutationFn: () => {
            const parsed = Number(maxSubtasks);
            return decomposeTask(projectId, taskId, {
                max_subtasks: Number.isFinite(parsed) && parsed > 0 ? Math.min(10, Math.max(1, parsed)) : 4,
                context: context.trim() || undefined,
            });
        },
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.subtasks(taskId) });
            await queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.projectTasks(projectId) });
            showToast({ message: "Task decomposed into subtasks.", severity: "success" });
        },
        onError: (error) => showToast({ message: extractApiErrorMessage(error, "Couldn't break task into subtasks. Try again."), severity: "error" }),
    });

    return (
        <Box>
            <Stack spacing={1} sx={{ mb: 1.5 }}>
                <Typography variant="caption" color="text.secondary">Subtasks of: {taskTitle}</Typography>
                <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
                    <TextField size="small" label="Context" value={context} onChange={(e) => setContext(e.target.value)} placeholder="payments, onboarding, migration..." fullWidth />
                    <TextField size="small" label="Max" type="number" value={maxSubtasks} onChange={(e) => setMaxSubtasks(e.target.value)} sx={{ width: { xs: "100%", sm: 96 } }} />
                    <Button size="small" startIcon={decomposeMutation.isPending ? <CircularProgress size={12} /> : <DecomposeIcon />} disabled={decomposeMutation.isPending} onClick={() => decomposeMutation.mutate()}>Decompose</Button>
                </Stack>
            </Stack>
            {isLoading ? <CircularProgress size={16} /> : subtasks.length === 0 ? (
                <Typography variant="caption" color="text.secondary">No subtasks yet.</Typography>
            ) : (
                <Stack spacing={0.5}>
                    {subtasks.map((sub) => (
                        <Stack key={sub.id} direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                            <Chip label={sub.status} size="small" variant="outlined" />
                            {sub.metadata.parallelizable ? <Chip label="parallel" size="small" color="info" variant="outlined" /> : null}
                            {typeof sub.metadata.blueprint_kind === "string" ? <Chip label={String(sub.metadata.blueprint_kind)} size="small" variant="outlined" /> : null}
                            <Typography variant="body2">{sub.title}</Typography>
                        </Stack>
                    ))}
                </Stack>
            )}
        </Box>
    );
}
