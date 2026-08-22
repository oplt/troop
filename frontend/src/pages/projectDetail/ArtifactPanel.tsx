import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Chip, Paper, Stack, TextField, Typography } from "@mui/material";
import { Upload as UploadIcon } from "@mui/icons-material";
import { createTaskArtifact, listTaskArtifacts } from "../../api/orchestration";
import { queryKeys } from "../../config/queryKeys";
import { formatDateTime } from "../../utils/formatters";

export function ArtifactPanel({ projectId, taskId }: { projectId: string; taskId: string }) {
    const queryClient = useQueryClient();
    const [title, setTitle] = useState("");
    const [content, setContent] = useState("");
    const fileRef = useRef<HTMLInputElement>(null);

    const { data: artifacts = [] } = useQuery({
        queryKey: queryKeys.orchestration.artifacts(taskId),
        queryFn: () => listTaskArtifacts(projectId, taskId),
    });

    const createMutation = useMutation({
        mutationFn: () => createTaskArtifact(projectId, taskId, { title, content, kind: "summary" }),
        onSuccess: async () => {
            setTitle(""); setContent("");
            await queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.artifacts(taskId) });
        },
    });

    async function handleFileUpload(file: File) {
        const text = await file.text();
        await createTaskArtifact(projectId, taskId, { title: file.name, content: text, kind: "file" });
        await queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.artifacts(taskId) });
    }

    return (
        <Stack spacing={1.5}>
            {artifacts.map((artifact) => (
                <Paper key={artifact.id} sx={{ p: 1.5, borderRadius: 1 }}>
                    <Stack direction="row" spacing={1} alignItems="center">
                        <Chip label={artifact.kind} size="small" variant="outlined" />
                        <Typography variant="subtitle2">{artifact.title}</Typography>
                        <Typography variant="caption" color="text.secondary">{formatDateTime(artifact.created_at)}</Typography>
                    </Stack>
                    {artifact.content && (
                        <Typography variant="caption" component="pre" sx={{ mt: 0.5, whiteSpace: "pre-wrap", wordBreak: "break-all", maxHeight: 120, overflow: "auto" }}>
                            {artifact.content.slice(0, 500)}
                        </Typography>
                    )}
                </Paper>
            ))}
            <Stack spacing={1}>
                <TextField size="small" label="Title" value={title} onChange={(e) => setTitle(e.target.value)} />
                <TextField size="small" label="Content" multiline minRows={2} value={content} onChange={(e) => setContent(e.target.value)} />
                <Stack direction="row" spacing={1}>
                    <Button size="small" variant="outlined" disabled={!title.trim()} onClick={() => createMutation.mutate()}>
                        Add artifact
                    </Button>
                    <Button size="small" variant="outlined" startIcon={<UploadIcon />} component="label">
                        Upload file
                        <input hidden type="file" ref={fileRef} onChange={(e) => {
                            const file = e.target.files?.[0];
                            if (file) void handleFileUpload(file);
                        }} />
                    </Button>
                </Stack>
            </Stack>
        </Stack>
    );
}
