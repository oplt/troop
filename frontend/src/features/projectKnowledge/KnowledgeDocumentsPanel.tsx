import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Box, Button, Chip, CircularProgress, Paper, Stack, Typography } from "@mui/material";
import { Refresh as ReindexIcon, Upload as UploadIcon } from "@mui/icons-material";

import {
    deleteRagDocument,
    listRagDocuments,
    reindexRagDocument,
    uploadRagDocument,
    type RagDocument,
} from "../../api/rag";
import { useSnackbar } from "../../app/snackbarContext";
import { toastError, toastSuccess } from "../../app/mutationToast";
import { ConfirmDestructiveDialog } from "../../components/ui/ConfirmDestructiveDialog";
import { SectionCard } from "../../components/ui/SectionCard";
import { queryKeys } from "../../config/queryKeys";
import { formatDateTime, humanizeKey } from "../../utils/formatters";

export function KnowledgeDocumentsPanel({ projectId }: { projectId: string }) {
    const [deleteTarget, setDeleteTarget] = useState<RagDocument | null>(null);
    const queryClient = useQueryClient();
    const { showToast } = useSnackbar();
    const documentsQuery = useQuery({
        queryKey: queryKeys.rag.documents(projectId),
        queryFn: () => listRagDocuments(projectId),
        enabled: Boolean(projectId),
    });
    const refreshDocuments = async () => {
        await queryClient.invalidateQueries({ queryKey: queryKeys.rag.documents(projectId) });
        await queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.projectDocuments(projectId) });
    };
    const upload = useMutation({
        mutationFn: (file: File) => uploadRagDocument(projectId, file),
        onSuccess: async () => {
            await refreshDocuments();
            toastSuccess(showToast, "Document uploaded and queued for indexing.");
        },
        onError: (error) => toastError(showToast, error, "Could not upload the document."),
    });
    const reindex = useMutation({
        mutationFn: (documentId: string) => reindexRagDocument(projectId, documentId),
        onSuccess: async () => {
            await refreshDocuments();
            toastSuccess(showToast, "Document reindexed.");
        },
        onError: (error) => toastError(showToast, error, "Could not reindex the document."),
    });
    const remove = useMutation({
        mutationFn: (documentId: string) => deleteRagDocument(projectId, documentId),
        onSuccess: async () => {
            setDeleteTarget(null);
            await refreshDocuments();
            toastSuccess(showToast, "Document removed.");
        },
        onError: (error) => toastError(showToast, error, "Could not remove the document."),
    });
    const documents = documentsQuery.data ?? [];

    return (
        <SectionCard
            title="Documents"
            description="Project-scoped sources used to ground answers and agent work."
            action={(
                <Button component="label" variant="contained" startIcon={<UploadIcon />} disabled={upload.isPending}>
                    {upload.isPending ? "Uploading…" : "Upload"}
                    <input
                        hidden
                        type="file"
                        accept=".txt,.md,.html,.json,.csv,.pdf"
                        onChange={(event) => {
                            const file = event.currentTarget.files?.[0];
                            if (file) upload.mutate(file);
                            event.currentTarget.value = "";
                        }}
                    />
                </Button>
            )}
        >
            {documentsQuery.isLoading ? <CircularProgress size={24} /> : null}
            {documentsQuery.isError ? <Alert severity="error">Could not load project documents.</Alert> : null}
            {!documentsQuery.isLoading && documents.length === 0 ? (
                <Box sx={{ py: 5, textAlign: "center" }}>
                    <Typography variant="subtitle1">No knowledge documents yet</Typography>
                    <Typography variant="body2" color="text.secondary">
                        Upload a focused source such as a brief, runbook, or specification.
                    </Typography>
                </Box>
            ) : (
                <Stack spacing={1}>
                    {documents.map((document) => (
                        <Paper key={document.document_id} variant="outlined" sx={{ p: 2, borderRadius: 1 }}>
                            <Stack direction={{ xs: "column", md: "row" }} spacing={2} justifyContent="space-between">
                                <Box sx={{ minWidth: 0 }}>
                                    <Typography variant="subtitle2" noWrap>{document.title}</Typography>
                                    <Typography variant="caption" color="text.secondary">
                                        Updated {formatDateTime(document.updated_at)}
                                    </Typography>
                                    <Stack direction="row" spacing={0.75} useFlexGap flexWrap="wrap" sx={{ mt: 1 }}>
                                        <Chip size="small" label={humanizeKey(document.ingestion_status)} />
                                        <Chip size="small" variant="outlined" label={`${document.chunk_count} chunks`} />
                                        <Chip size="small" variant="outlined" label={humanizeKey(document.source_type)} />
                                    </Stack>
                                </Box>
                                <Stack direction="row" spacing={1} alignItems="center">
                                    <Button
                                        size="small"
                                        startIcon={<ReindexIcon />}
                                        disabled={reindex.isPending}
                                        onClick={() => reindex.mutate(document.document_id)}
                                    >
                                        Reindex
                                    </Button>
                                    <Button size="small" color="error" onClick={() => setDeleteTarget(document)}>
                                        Delete
                                    </Button>
                                </Stack>
                            </Stack>
                        </Paper>
                    ))}
                </Stack>
            )}
            <ConfirmDestructiveDialog
                open={Boolean(deleteTarget)}
                title="Delete knowledge document?"
                description={`“${deleteTarget?.title ?? "This document"}” and its indexed chunks will be removed.`}
                loading={remove.isPending}
                onClose={() => setDeleteTarget(null)}
                onConfirm={() => deleteTarget && remove.mutate(deleteTarget.document_id)}
            />
        </SectionCard>
    );
}
