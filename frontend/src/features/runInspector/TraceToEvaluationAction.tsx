import { useState } from "react";
import { Link as RouterLink } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
    Alert,
    Button,
    Dialog,
    DialogActions,
    DialogContent,
    DialogTitle,
    MenuItem,
    Stack,
    TextField,
} from "@mui/material";

import { createAiDatasetCaseFromTrace, listAiDatasets } from "../../api/ai";
import type { RunTraceSpan } from "../../api/orchestration";
import { useSnackbar } from "../../app/snackbarContext";
import { toastError, toastSuccess } from "../../app/mutationToast";
import { queryKeys } from "../../config/queryKeys";

type TraceToEvaluationActionProps = {
    runId: string;
    spans: RunTraceSpan[];
};

function parseOptionalObject(value: string, label: string): Record<string, unknown> | undefined {
    if (!value.trim()) return undefined;
    const parsed: unknown = JSON.parse(value);
    if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
        throw new Error(`${label} must be a JSON object.`);
    }
    return parsed as Record<string, unknown>;
}

export function TraceToEvaluationAction({ runId, spans }: TraceToEvaluationActionProps) {
    const [open, setOpen] = useState(false);
    const [datasetId, setDatasetId] = useState("");
    const [spanId, setSpanId] = useState("");
    const [expectedText, setExpectedText] = useState("");
    const [expectedJson, setExpectedJson] = useState("");
    const [assertionsJson, setAssertionsJson] = useState("");
    const [notes, setNotes] = useState("");
    const queryClient = useQueryClient();
    const { showToast } = useSnackbar();

    const datasetsQuery = useQuery({
        queryKey: queryKeys.ai.datasets,
        queryFn: listAiDatasets,
        enabled: open,
    });

    const createCase = useMutation({
        mutationFn: async () => {
            if (!datasetId) throw new Error("Choose an evaluation dataset.");
            const expectedOutputJson = parseOptionalObject(expectedJson, "Expected JSON");
            const expectedAssertions = parseOptionalObject(assertionsJson, "Expected assertions");
            return createAiDatasetCaseFromTrace(datasetId, {
                run_id: runId,
                source_trace_span_id: spanId || null,
                correction: {
                    expected_output_text: expectedText || null,
                    expected_output_json: expectedOutputJson ?? null,
                },
                expected_assertions: expectedAssertions ?? null,
                notes: notes || null,
            });
        },
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: queryKeys.ai.datasetCases(datasetId) });
            toastSuccess(showToast, "Trace added to the evaluation dataset.");
            setOpen(false);
        },
        onError: (error) => toastError(showToast, error, "Could not create an evaluation case."),
    });

    const datasets = datasetsQuery.data ?? [];

    return (
        <>
            <Button size="small" variant="outlined" onClick={() => setOpen(true)}>
                Add to evaluation
            </Button>
            <Dialog open={open} onClose={() => setOpen(false)} fullWidth maxWidth="sm">
                <DialogTitle>Add production trace to an evaluation</DialogTitle>
                <DialogContent>
                    <Stack spacing={2} sx={{ pt: 1 }}>
                        <Alert severity="info">
                            Secrets and personal data are redacted on the server. The case keeps run, model, prompt,
                            workflow, skill, and selected-span provenance.
                        </Alert>
                        {datasetsQuery.isError && <Alert severity="error">Could not load evaluation datasets.</Alert>}
                        {datasets.length === 0 && !datasetsQuery.isLoading ? (
                            <Alert severity="warning">
                                Create a dataset in <Button component={RouterLink} to="/ai" size="small">AI Studio</Button> first.
                            </Alert>
                        ) : (
                            <TextField
                                select
                                label="Evaluation dataset"
                                value={datasetId}
                                onChange={(event) => setDatasetId(event.target.value)}
                                required
                                fullWidth
                            >
                                {datasets.map((dataset) => (
                                    <MenuItem key={dataset.id} value={dataset.id}>{dataset.name}</MenuItem>
                                ))}
                            </TextField>
                        )}
                        <TextField
                            select
                            label="Trace scope"
                            value={spanId}
                            onChange={(event) => setSpanId(event.target.value)}
                            helperText="Use the whole run, or anchor the case to one safe trace span."
                            fullWidth
                        >
                            <MenuItem value="">Whole run</MenuItem>
                            {spans.map((span) => (
                                <MenuItem key={span.id} value={span.id}>{span.title}</MenuItem>
                            ))}
                        </TextField>
                        <TextField
                            label="Correct expected text"
                            value={expectedText}
                            onChange={(event) => setExpectedText(event.target.value)}
                            multiline
                            minRows={2}
                            fullWidth
                        />
                        <TextField
                            label="Correct expected JSON"
                            value={expectedJson}
                            onChange={(event) => setExpectedJson(event.target.value)}
                            placeholder='{"result":"expected"}'
                            multiline
                            minRows={2}
                            fullWidth
                        />
                        <TextField
                            label="Expected assertions JSON"
                            value={assertionsJson}
                            onChange={(event) => setAssertionsJson(event.target.value)}
                            placeholder='{"mode":"deterministic","rules":[]}'
                            multiline
                            minRows={2}
                            fullWidth
                        />
                        <TextField label="Notes" value={notes} onChange={(event) => setNotes(event.target.value)} fullWidth />
                    </Stack>
                </DialogContent>
                <DialogActions>
                    <Button onClick={() => setOpen(false)}>Cancel</Button>
                    <Button
                        variant="contained"
                        disabled={!datasetId || createCase.isPending}
                        onClick={() => createCase.mutate()}
                    >
                        {createCase.isPending ? "Adding…" : "Add case"}
                    </Button>
                </DialogActions>
            </Dialog>
        </>
    );
}
