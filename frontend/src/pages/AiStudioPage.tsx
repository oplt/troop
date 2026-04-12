import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
    Alert,
    Box,
    Button,
    Chip,
    FormControlLabel,
    MenuItem,
    Skeleton,
    Stack,
    Switch,
    TextField,
    Typography,
} from "@mui/material";
import {
    Approval as ReviewIcon,
    AutoAwesome as AiIcon,
    Dataset as DatasetIcon,
    Description as DocumentIcon,
    PlayCircleOutline as RunIcon,
    PsychologyAlt as PromptIcon,
} from "@mui/icons-material";
import {
    createAiDataset,
    createAiDatasetCase,
    createAiDocument,
    createAiFeedback,
    createAiReview,
    createAiRun,
    createPromptTemplate,
    createPromptVersion,
    decideAiReview,
    getAiOverview,
    listAiDatasetCases,
    listAiEvaluationRuns,
    listAiReviews,
    listPromptVersions,
    runAiEvaluation,
    updatePromptTemplate,
    updatePromptVersion,
    uploadAiDocument,
} from "../api/ai";
import { useSnackbar } from "../app/snackbarContext";
import { EmptyState } from "../components/ui/EmptyState";
import { PageHeader } from "../components/ui/PageHeader";
import { PageShell } from "../components/ui/PageShell";
import { SectionCard } from "../components/ui/SectionCard";
import { StatCard } from "../components/ui/StatCard";
import { formatCurrency, formatDateTime } from "../utils/formatters";

function parseJsonObject(value: string, fallback: Record<string, unknown> = {}) {
    if (!value.trim()) {
        return fallback;
    }
    const parsed = JSON.parse(value);
    if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
        throw new Error("JSON payload must be an object.");
    }
    return parsed as Record<string, unknown>;
}

function formatCostMicros(micros: number) {
    return formatCurrency(micros / 10000, "USD");
}

export default function AiStudioPage() {
    const queryClient = useQueryClient();
    const { showToast } = useSnackbar();
    const { data: overview, isLoading } = useQuery({
        queryKey: ["ai", "overview"],
        queryFn: getAiOverview,
    });
    const { data: reviews = [] } = useQuery({
        queryKey: ["ai", "reviews"],
        queryFn: listAiReviews,
    });
    const { data: evaluationRuns = [] } = useQuery({
        queryKey: ["ai", "evaluation-runs"],
        queryFn: listAiEvaluationRuns,
    });

    const [selectedTemplateId, setSelectedTemplateId] = useState("");
    const [selectedDatasetId, setSelectedDatasetId] = useState("");
    const [selectedDocumentIds, setSelectedDocumentIds] = useState<string[]>([]);
    const [templateForm, setTemplateForm] = useState({ key: "", name: "", description: "" });
    const [versionForm, setVersionForm] = useState({
        provider_key: "local",
        model_name: "local-heuristic",
        system_prompt: "",
        user_prompt_template: "",
        variable_names: "",
        response_format: "text" as "text" | "json",
        temperature: "0.2",
        rollout_percentage: "100",
        is_published: true,
        input_cost_per_million: "0",
        output_cost_per_million: "0",
    });
    const [textDocumentForm, setTextDocumentForm] = useState({
        title: "",
        description: "",
        content: "",
        content_type: "text/plain",
    });
    const [uploadDescription, setUploadDescription] = useState("");
    const [runForm, setRunForm] = useState({
        prompt_template_key: "",
        prompt_version_id: "",
        variables_json: "{\n  \"task\": \"Summarize the attached knowledge base\"\n}",
        retrieval_query: "",
        top_k: "4",
        review_required: false,
    });
    const [reviewNotesById, setReviewNotesById] = useState<Record<string, string>>({});
    const [correctionsById, setCorrectionsById] = useState<Record<string, string>>({});
    const [feedbackCommentByRunId, setFeedbackCommentByRunId] = useState<Record<string, string>>({});
    const [datasetForm, setDatasetForm] = useState({ name: "", description: "" });
    const [datasetCaseForm, setDatasetCaseForm] = useState({
        input_variables_json: "{\n  \"task\": \"What is the return policy?\"\n}",
        expected_output_text: "",
        expected_output_json: "",
        notes: "",
    });

    const promptTemplates = overview?.prompt_templates ?? [];
    const documents = overview?.documents ?? [];
    const datasets = overview?.datasets ?? [];
    const recentRuns = overview?.recent_runs ?? [];
    const providers = overview?.providers ?? [];

    const { data: selectedTemplateVersions = [] } = useQuery({
        queryKey: ["ai", "prompt-versions", selectedTemplateId],
        queryFn: () => listPromptVersions(selectedTemplateId),
        enabled: selectedTemplateId.length > 0,
    });
    const { data: selectedDatasetCases = [] } = useQuery({
        queryKey: ["ai", "dataset-cases", selectedDatasetId],
        queryFn: () => listAiDatasetCases(selectedDatasetId),
        enabled: selectedDatasetId.length > 0,
    });

    const templateKeyOptions = promptTemplates.map((template) => ({
        id: template.id,
        key: template.key,
        name: template.name,
    }));

    const createTemplateMutation = useMutation({
        mutationFn: createPromptTemplate,
        onSuccess: async () => {
            setTemplateForm({ key: "", name: "", description: "" });
            await queryClient.invalidateQueries({ queryKey: ["ai"] });
            showToast({ message: "Prompt template created.", severity: "success" });
        },
    });
    const createVersionMutation = useMutation({
        mutationFn: ({
            templateId,
            payload,
        }: {
            templateId: string;
            payload: Parameters<typeof createPromptVersion>[1];
        }) => createPromptVersion(templateId, payload),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["ai"] });
            await queryClient.invalidateQueries({ queryKey: ["ai", "prompt-versions", selectedTemplateId] });
            showToast({ message: "Prompt version created.", severity: "success" });
        },
    });
    const activateVersionMutation = useMutation({
        mutationFn: ({ templateId, versionId }: { templateId: string; versionId: string }) =>
            updatePromptTemplate(templateId, { active_version_id: versionId }),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["ai"] });
            showToast({ message: "Active prompt version updated.", severity: "success" });
        },
    });
    const publishVersionMutation = useMutation({
        mutationFn: ({
            templateId,
            versionId,
            isPublished,
        }: {
            templateId: string;
            versionId: string;
            isPublished: boolean;
        }) => updatePromptVersion(templateId, versionId, { is_published: isPublished }),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["ai", "prompt-versions", selectedTemplateId] });
            showToast({ message: "Prompt version updated.", severity: "success" });
        },
    });
    const createTextDocumentMutation = useMutation({
        mutationFn: createAiDocument,
        onSuccess: async () => {
            setTextDocumentForm({ title: "", description: "", content: "", content_type: "text/plain" });
            await queryClient.invalidateQueries({ queryKey: ["ai"] });
            showToast({ message: "Document ingested.", severity: "success" });
        },
    });
    const uploadDocumentMutation = useMutation({
        mutationFn: ({ file, description }: { file: File; description?: string }) =>
            uploadAiDocument(file, description),
        onSuccess: async () => {
            setUploadDescription("");
            await queryClient.invalidateQueries({ queryKey: ["ai"] });
            showToast({ message: "Document uploaded and chunked.", severity: "success" });
        },
    });
    const createRunMutation = useMutation({
        mutationFn: createAiRun,
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["ai"] });
            await queryClient.invalidateQueries({ queryKey: ["ai", "reviews"] });
            showToast({ message: "AI run completed.", severity: "success" });
        },
    });
    const createReviewMutation = useMutation({
        mutationFn: (runId: string) => createAiReview(runId),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["ai", "reviews"] });
            await queryClient.invalidateQueries({ queryKey: ["ai"] });
            showToast({ message: "Review requested.", severity: "success" });
        },
    });
    const decideReviewMutation = useMutation({
        mutationFn: ({
            reviewId,
            status,
            reviewer_notes,
            corrected_output,
        }: {
            reviewId: string;
            status: "approved" | "rejected" | "changes_requested";
            reviewer_notes?: string;
            corrected_output?: string;
        }) => decideAiReview(reviewId, { status, reviewer_notes, corrected_output }),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["ai", "reviews"] });
            await queryClient.invalidateQueries({ queryKey: ["ai"] });
            showToast({ message: "Review decision saved.", severity: "success" });
        },
    });
    const createFeedbackMutation = useMutation({
        mutationFn: ({
            runId,
            rating,
            comment,
            corrected_output,
        }: {
            runId: string;
            rating: -1 | 1;
            comment?: string;
            corrected_output?: string;
        }) => createAiFeedback(runId, { rating, comment, corrected_output }),
        onSuccess: async () => {
            showToast({ message: "Feedback saved.", severity: "success" });
        },
    });
    const createDatasetMutation = useMutation({
        mutationFn: createAiDataset,
        onSuccess: async (dataset) => {
            setDatasetForm({ name: "", description: "" });
            setSelectedDatasetId(dataset.id);
            await queryClient.invalidateQueries({ queryKey: ["ai"] });
            showToast({ message: "Evaluation dataset created.", severity: "success" });
        },
    });
    const createDatasetCaseMutation = useMutation({
        mutationFn: ({
            datasetId,
            payload,
        }: {
            datasetId: string;
            payload: Parameters<typeof createAiDatasetCase>[1];
        }) => createAiDatasetCase(datasetId, payload),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["ai", "dataset-cases", selectedDatasetId] });
            showToast({ message: "Evaluation case added.", severity: "success" });
        },
    });
    const runEvaluationMutation = useMutation({
        mutationFn: ({ datasetId, promptVersionId }: { datasetId: string; promptVersionId: string }) =>
            runAiEvaluation(datasetId, promptVersionId),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["ai", "evaluation-runs"] });
            await queryClient.invalidateQueries({ queryKey: ["ai"] });
            showToast({ message: "Evaluation run completed.", severity: "success" });
        },
    });

    function parseVariableDefinitions(rawNames: string) {
        return rawNames
            .split(",")
            .map((item) => item.trim())
            .filter(Boolean)
            .map((name) => ({ name, description: null, required: true }));
    }

    function toggleDocument(documentId: string) {
        setSelectedDocumentIds((current) =>
            current.includes(documentId)
                ? current.filter((item) => item !== documentId)
                : [...current, documentId]
        );
    }

    if (isLoading) {
        return (
            <Box sx={{ display: "grid", placeItems: "center", minHeight: "100vh" }}>
                <Skeleton variant="rounded" width="92%" height={520} sx={{ borderRadius: 6 }} />
            </Box>
        );
    }

    return (
        <PageShell maxWidth="xl">
            <PageHeader
                eyebrow="AI platform"
                title="AI Studio"
                description="Manage prompt versions, retrieval documents, review queues, evaluation datasets, and reusable AI run telemetry from one place."
                meta={
                    <>
                        <Chip label={`${providers.length} providers`} variant="outlined" />
                        <Chip label={`${recentRuns.length} recent runs`} variant="outlined" />
                        <Chip label={`${documents.length} documents`} variant="outlined" />
                    </>
                }
            />

            <Box
                sx={{
                    display: "grid",
                    gap: 2,
                    gridTemplateColumns: { xs: "1fr", sm: "repeat(2, minmax(0, 1fr))", xl: "repeat(4, minmax(0, 1fr))" },
                }}
            >
                <StatCard label="Prompt templates" value={promptTemplates.length} description="Reusable prompts with version history" icon={<PromptIcon />} />
                <StatCard label="Documents" value={documents.length} description="Indexed retrieval sources" icon={<DocumentIcon />} color="secondary" />
                <StatCard label="Pending reviews" value={reviews.filter((item) => item.status === "pending").length} description="Runs waiting for human review" icon={<ReviewIcon />} color="warning" />
                <StatCard label="Datasets" value={datasets.length} description="Saved evaluation datasets" icon={<DatasetIcon />} color="success" />
            </Box>

            <Box
                sx={{
                    mt: 2,
                    display: "grid",
                    gap: 2,
                    gridTemplateColumns: { xs: "1fr", xl: "1.1fr 0.9fr" },
                    alignItems: "start",
                }}
            >
                <Stack spacing={2}>
                    <SectionCard title="Prompt library" description="Create reusable prompt templates and publish versioned variants with rollout and pricing metadata.">
                        <Stack spacing={2}>
                            <Stack direction={{ xs: "column", md: "row" }} spacing={1.5}>
                                <TextField label="Template key" value={templateForm.key} onChange={(event) => setTemplateForm((current) => ({ ...current, key: event.target.value }))} fullWidth />
                                <TextField label="Name" value={templateForm.name} onChange={(event) => setTemplateForm((current) => ({ ...current, name: event.target.value }))} fullWidth />
                            </Stack>
                            <TextField label="Description" value={templateForm.description} onChange={(event) => setTemplateForm((current) => ({ ...current, description: event.target.value }))} fullWidth multiline minRows={2} />
                            <Button
                                variant="contained"
                                onClick={() => createTemplateMutation.mutate(templateForm)}
                                disabled={createTemplateMutation.isPending || !templateForm.key.trim() || !templateForm.name.trim()}
                            >
                                {createTemplateMutation.isPending ? "Creating..." : "Create prompt template"}
                            </Button>
                            {promptTemplates.length > 0 ? (
                                <Stack spacing={1.25}>
                                    {promptTemplates.map((template) => (
                                        <Box key={template.id} sx={(theme) => ({ p: 2, borderRadius: 4, border: `1px solid ${theme.palette.divider}` })}>
                                            <Stack spacing={1}>
                                                <Stack direction={{ xs: "column", sm: "row" }} justifyContent="space-between" spacing={1}>
                                                    <Box>
                                                        <Typography variant="subtitle1">{template.name}</Typography>
                                                        <Typography variant="body2" color="text.secondary">
                                                            {template.key}
                                                        </Typography>
                                                    </Box>
                                                    <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                                                        {template.is_active && <Chip label="active" size="small" color="success" variant="outlined" />}
                                                        {template.active_version_id && <Chip label="version pinned" size="small" variant="outlined" />}
                                                    </Stack>
                                                </Stack>
                                                {template.description && (
                                                    <Typography variant="body2" color="text.secondary">
                                                        {template.description}
                                                    </Typography>
                                                )}
                                                <Button variant="outlined" size="small" onClick={() => setSelectedTemplateId(template.id)}>
                                                    {selectedTemplateId === template.id ? "Selected" : "Manage versions"}
                                                </Button>
                                            </Stack>
                                        </Box>
                                    ))}
                                </Stack>
                            ) : (
                                <EmptyState
                                    icon={<PromptIcon />}
                                    title="No prompts yet"
                                    description="Create your first prompt template to start building reusable AI behaviors."
                                />
                            )}
                        </Stack>
                    </SectionCard>

                    <SectionCard title="Run playground" description="Execute prompt versions with structured variables, retrieval context, and human-review routing.">
                        <Stack spacing={2}>
                            <TextField
                                select
                                label="Prompt template"
                                value={runForm.prompt_template_key}
                                onChange={(event) => setRunForm((current) => ({ ...current, prompt_template_key: event.target.value }))}
                                fullWidth
                            >
                                {templateKeyOptions.map((template) => (
                                    <MenuItem key={template.id} value={template.key}>
                                        {template.name} ({template.key})
                                    </MenuItem>
                                ))}
                            </TextField>
                            <TextField
                                label="Variables JSON"
                                value={runForm.variables_json}
                                onChange={(event) => setRunForm((current) => ({ ...current, variables_json: event.target.value }))}
                                fullWidth
                                multiline
                                minRows={8}
                            />
                            <TextField
                                label="Retrieval query"
                                value={runForm.retrieval_query}
                                onChange={(event) => setRunForm((current) => ({ ...current, retrieval_query: event.target.value }))}
                                fullWidth
                            />
                            <TextField
                                label="Top K chunks"
                                value={runForm.top_k}
                                onChange={(event) => setRunForm((current) => ({ ...current, top_k: event.target.value }))}
                                fullWidth
                            />
                            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                                {documents.map((document) => (
                                    <Chip
                                        key={document.id}
                                        label={document.title}
                                        color={selectedDocumentIds.includes(document.id) ? "primary" : "default"}
                                        variant={selectedDocumentIds.includes(document.id) ? "filled" : "outlined"}
                                        onClick={() => toggleDocument(document.id)}
                                    />
                                ))}
                            </Stack>
                            <FormControlLabel
                                control={
                                    <Switch
                                        checked={runForm.review_required}
                                        onChange={(event) => setRunForm((current) => ({ ...current, review_required: event.target.checked }))}
                                    />
                                }
                                label="Request human review after this run"
                            />
                            <Button
                                variant="contained"
                                startIcon={<RunIcon />}
                                disabled={createRunMutation.isPending || !runForm.prompt_template_key}
                                onClick={() => {
                                    try {
                                        createRunMutation.mutate({
                                            prompt_template_key: runForm.prompt_template_key,
                                            variables: parseJsonObject(runForm.variables_json),
                                            retrieval_query: runForm.retrieval_query || undefined,
                                            document_ids: selectedDocumentIds,
                                            top_k: Number(runForm.top_k || 4),
                                            review_required: runForm.review_required,
                                        });
                                    } catch (error) {
                                        showToast({
                                            message: error instanceof Error ? error.message : "Invalid variables JSON.",
                                            severity: "error",
                                        });
                                    }
                                }}
                            >
                                {createRunMutation.isPending ? "Running..." : "Run prompt"}
                            </Button>
                            {recentRuns.length > 0 ? (
                                <Stack spacing={1.25}>
                                    {recentRuns.map((run) => (
                                        <Box key={run.id} sx={(theme) => ({ p: 2, borderRadius: 4, border: `1px solid ${theme.palette.divider}` })}>
                                            <Stack spacing={1}>
                                                <Stack direction={{ xs: "column", sm: "row" }} justifyContent="space-between" spacing={1}>
                                                    <Typography variant="subtitle2">
                                                        {run.provider_key}/{run.model_name}
                                                    </Typography>
                                                    <Chip label={run.status} size="small" color={run.status === "completed" ? "success" : "warning"} variant="outlined" />
                                                </Stack>
                                                <Typography variant="body2" color="text.secondary">
                                                    {run.output_text?.slice(0, 280) || JSON.stringify(run.output_json, null, 2).slice(0, 280) || "No output"}
                                                </Typography>
                                                <Typography variant="caption" color="text.secondary">
                                                    {formatDateTime(run.created_at)} • {run.total_tokens} tokens • {formatCostMicros(run.estimated_cost_micros)}
                                                </Typography>
                                                <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
                                                    <Button size="small" variant="outlined" onClick={() => createReviewMutation.mutate(run.id)}>
                                                        Request review
                                                    </Button>
                                                    <Button
                                                        size="small"
                                                        variant="outlined"
                                                        color="success"
                                                        onClick={() => createFeedbackMutation.mutate({
                                                            runId: run.id,
                                                            rating: 1,
                                                            comment: feedbackCommentByRunId[run.id],
                                                        })}
                                                    >
                                                        Thumbs up
                                                    </Button>
                                                    <Button
                                                        size="small"
                                                        variant="outlined"
                                                        color="warning"
                                                        onClick={() => createFeedbackMutation.mutate({
                                                            runId: run.id,
                                                            rating: -1,
                                                            comment: feedbackCommentByRunId[run.id],
                                                            corrected_output: correctionsById[run.id],
                                                        })}
                                                    >
                                                        Thumbs down
                                                    </Button>
                                                </Stack>
                                                <TextField
                                                    label="Feedback note"
                                                    value={feedbackCommentByRunId[run.id] ?? ""}
                                                    onChange={(event) =>
                                                        setFeedbackCommentByRunId((current) => ({ ...current, [run.id]: event.target.value }))
                                                    }
                                                    fullWidth
                                                    size="small"
                                                />
                                                <TextField
                                                    label="Correction"
                                                    value={correctionsById[run.id] ?? ""}
                                                    onChange={(event) =>
                                                        setCorrectionsById((current) => ({ ...current, [run.id]: event.target.value }))
                                                    }
                                                    fullWidth
                                                    size="small"
                                                    multiline
                                                    minRows={2}
                                                />
                                            </Stack>
                                        </Box>
                                    ))}
                                </Stack>
                            ) : (
                                <EmptyState icon={<AiIcon />} title="No AI runs yet" description="Run a prompt version to capture outputs, token usage, and review state." />
                            )}
                        </Stack>
                    </SectionCard>
                </Stack>

                <Stack spacing={2}>
                    <SectionCard title="Version builder" description="Attach deployable versions to a prompt template with model selection, rollout state, and provider pricing.">
                        <Stack spacing={2}>
                            <TextField
                                select
                                label="Selected template"
                                value={selectedTemplateId}
                                onChange={(event) => setSelectedTemplateId(event.target.value)}
                                fullWidth
                            >
                                {promptTemplates.map((template) => (
                                    <MenuItem key={template.id} value={template.id}>
                                        {template.name}
                                    </MenuItem>
                                ))}
                            </TextField>
                            <TextField
                                select
                                label="Provider"
                                value={versionForm.provider_key}
                                onChange={(event) => setVersionForm((current) => ({ ...current, provider_key: event.target.value }))}
                                fullWidth
                            >
                                {providers.map((provider) => (
                                    <MenuItem key={provider.key} value={provider.key}>
                                        {provider.label}
                                    </MenuItem>
                                ))}
                            </TextField>
                            <TextField label="Model name" value={versionForm.model_name} onChange={(event) => setVersionForm((current) => ({ ...current, model_name: event.target.value }))} fullWidth />
                            <TextField label="System prompt" value={versionForm.system_prompt} onChange={(event) => setVersionForm((current) => ({ ...current, system_prompt: event.target.value }))} fullWidth multiline minRows={3} />
                            <TextField label="User prompt template" value={versionForm.user_prompt_template} onChange={(event) => setVersionForm((current) => ({ ...current, user_prompt_template: event.target.value }))} fullWidth multiline minRows={5} />
                            <TextField label="Variable names (comma separated)" value={versionForm.variable_names} onChange={(event) => setVersionForm((current) => ({ ...current, variable_names: event.target.value }))} fullWidth />
                            <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5}>
                                <TextField select label="Response format" value={versionForm.response_format} onChange={(event) => setVersionForm((current) => ({ ...current, response_format: event.target.value as "text" | "json" }))} fullWidth>
                                    <MenuItem value="text">Text</MenuItem>
                                    <MenuItem value="json">JSON</MenuItem>
                                </TextField>
                                <TextField label="Temperature" value={versionForm.temperature} onChange={(event) => setVersionForm((current) => ({ ...current, temperature: event.target.value }))} fullWidth />
                            </Stack>
                            <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5}>
                                <TextField label="Rollout %" value={versionForm.rollout_percentage} onChange={(event) => setVersionForm((current) => ({ ...current, rollout_percentage: event.target.value }))} fullWidth />
                                <FormControlLabel control={<Switch checked={versionForm.is_published} onChange={(event) => setVersionForm((current) => ({ ...current, is_published: event.target.checked }))} />} label="Published" />
                            </Stack>
                            <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5}>
                                <TextField label="Input cost / million" value={versionForm.input_cost_per_million} onChange={(event) => setVersionForm((current) => ({ ...current, input_cost_per_million: event.target.value }))} fullWidth />
                                <TextField label="Output cost / million" value={versionForm.output_cost_per_million} onChange={(event) => setVersionForm((current) => ({ ...current, output_cost_per_million: event.target.value }))} fullWidth />
                            </Stack>
                            <Button
                                variant="contained"
                                disabled={createVersionMutation.isPending || !selectedTemplateId || !versionForm.model_name.trim() || !versionForm.user_prompt_template.trim()}
                                onClick={() =>
                                    createVersionMutation.mutate({
                                        templateId: selectedTemplateId,
                                        payload: {
                                            provider_key: versionForm.provider_key,
                                            model_name: versionForm.model_name,
                                            system_prompt: versionForm.system_prompt,
                                            user_prompt_template: versionForm.user_prompt_template,
                                            variable_definitions: parseVariableDefinitions(versionForm.variable_names),
                                            response_format: versionForm.response_format,
                                            temperature: Number(versionForm.temperature || 0.2),
                                            rollout_percentage: Number(versionForm.rollout_percentage || 100),
                                            is_published: versionForm.is_published,
                                            input_cost_per_million: Number(versionForm.input_cost_per_million || 0),
                                            output_cost_per_million: Number(versionForm.output_cost_per_million || 0),
                                        },
                                    })
                                }
                            >
                                {createVersionMutation.isPending ? "Saving..." : "Create prompt version"}
                            </Button>
                            {selectedTemplateVersions.length > 0 && (
                                <Stack spacing={1.25}>
                                    {selectedTemplateVersions.map((version) => (
                                        <Box key={version.id} sx={(theme) => ({ p: 2, borderRadius: 4, border: `1px solid ${theme.palette.divider}` })}>
                                            <Stack spacing={1}>
                                                <Stack direction={{ xs: "column", sm: "row" }} justifyContent="space-between" spacing={1}>
                                                    <Typography variant="subtitle2">
                                                        v{version.version_number} • {version.provider_key}/{version.model_name}
                                                    </Typography>
                                                    <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                                                        {version.is_published && <Chip label="published" size="small" color="success" variant="outlined" />}
                                                        <Chip label={`${version.rollout_percentage}% rollout`} size="small" variant="outlined" />
                                                    </Stack>
                                                </Stack>
                                                <Typography variant="body2" color="text.secondary">
                                                    {version.user_prompt_template.slice(0, 180)}
                                                </Typography>
                                                <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
                                                    <Button size="small" variant="outlined" onClick={() => activateVersionMutation.mutate({ templateId: selectedTemplateId, versionId: version.id })}>
                                                        Set active
                                                    </Button>
                                                    <Button
                                                        size="small"
                                                        variant="outlined"
                                                        onClick={() => publishVersionMutation.mutate({ templateId: selectedTemplateId, versionId: version.id, isPublished: !version.is_published })}
                                                    >
                                                        {version.is_published ? "Unpublish" : "Publish"}
                                                    </Button>
                                                </Stack>
                                            </Stack>
                                        </Box>
                                    ))}
                                </Stack>
                            )}
                        </Stack>
                    </SectionCard>

                    <SectionCard title="Retrieval documents" description="Ingest source files or direct text, chunk them, and use them as retrieval context in prompt runs.">
                        <Stack spacing={2}>
                            <TextField label="Document title" value={textDocumentForm.title} onChange={(event) => setTextDocumentForm((current) => ({ ...current, title: event.target.value }))} fullWidth />
                            <TextField label="Description" value={textDocumentForm.description} onChange={(event) => setTextDocumentForm((current) => ({ ...current, description: event.target.value }))} fullWidth />
                            <TextField label="Document content" value={textDocumentForm.content} onChange={(event) => setTextDocumentForm((current) => ({ ...current, content: event.target.value }))} fullWidth multiline minRows={6} />
                            <Button
                                variant="outlined"
                                disabled={createTextDocumentMutation.isPending || !textDocumentForm.title.trim() || !textDocumentForm.content.trim()}
                                onClick={() => createTextDocumentMutation.mutate(textDocumentForm)}
                            >
                                {createTextDocumentMutation.isPending ? "Ingesting..." : "Create text document"}
                            </Button>
                            <Button component="label" variant="contained" disabled={uploadDocumentMutation.isPending}>
                                {uploadDocumentMutation.isPending ? "Uploading..." : "Upload text/markdown/json file"}
                                <input
                                    hidden
                                    type="file"
                                    accept=".txt,.md,.json,.ndjson,text/plain,text/markdown,application/json"
                                    onChange={(event) => {
                                        const file = event.target.files?.[0];
                                        if (file) {
                                            uploadDocumentMutation.mutate({ file, description: uploadDescription || undefined });
                                        }
                                        event.currentTarget.value = "";
                                    }}
                                />
                            </Button>
                            <TextField label="Upload description" value={uploadDescription} onChange={(event) => setUploadDescription(event.target.value)} fullWidth />
                            {documents.length > 0 ? (
                                <Stack spacing={1}>
                                    {documents.map((document) => (
                                        <Box key={document.id} sx={(theme) => ({ p: 1.5, borderRadius: 3, border: `1px solid ${theme.palette.divider}` })}>
                                            <Typography variant="subtitle2">{document.title}</Typography>
                                            <Typography variant="caption" color="text.secondary">
                                                {document.chunk_count} chunks • {document.content_type} • {formatDateTime(document.updated_at)}
                                            </Typography>
                                        </Box>
                                    ))}
                                </Stack>
                            ) : (
                                <EmptyState icon={<DocumentIcon />} title="No documents indexed" description="Upload source material to power retrieval-augmented runs." />
                            )}
                        </Stack>
                    </SectionCard>

                    <SectionCard title="Reviews and evaluations" description="Route sensitive outputs through human approval and keep reusable benchmark datasets for prompt regression testing.">
                        <Stack spacing={2}>
                            <Stack spacing={1.25}>
                                <Typography variant="subtitle2">Review queue</Typography>
                                {reviews.length > 0 ? (
                                    reviews.map((review) => (
                                        <Box key={review.id} sx={(theme) => ({ p: 2, borderRadius: 4, border: `1px solid ${theme.palette.divider}` })}>
                                            <Stack spacing={1}>
                                                <Stack direction={{ xs: "column", sm: "row" }} justifyContent="space-between" spacing={1}>
                                                    <Typography variant="body2">Run {review.run_id.slice(0, 8)}</Typography>
                                                    <Chip label={review.status} size="small" variant="outlined" />
                                                </Stack>
                                                <TextField
                                                    label="Reviewer notes"
                                                    value={reviewNotesById[review.id] ?? ""}
                                                    onChange={(event) => setReviewNotesById((current) => ({ ...current, [review.id]: event.target.value }))}
                                                    fullWidth
                                                    size="small"
                                                />
                                                <TextField
                                                    label="Corrected output"
                                                    value={correctionsById[review.id] ?? ""}
                                                    onChange={(event) => setCorrectionsById((current) => ({ ...current, [review.id]: event.target.value }))}
                                                    fullWidth
                                                    size="small"
                                                    multiline
                                                    minRows={2}
                                                />
                                                <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
                                                    <Button size="small" variant="outlined" color="success" onClick={() => decideReviewMutation.mutate({ reviewId: review.id, status: "approved", reviewer_notes: reviewNotesById[review.id], corrected_output: correctionsById[review.id] })}>
                                                        Approve
                                                    </Button>
                                                    <Button size="small" variant="outlined" color="warning" onClick={() => decideReviewMutation.mutate({ reviewId: review.id, status: "changes_requested", reviewer_notes: reviewNotesById[review.id], corrected_output: correctionsById[review.id] })}>
                                                        Request changes
                                                    </Button>
                                                    <Button size="small" variant="outlined" color="error" onClick={() => decideReviewMutation.mutate({ reviewId: review.id, status: "rejected", reviewer_notes: reviewNotesById[review.id] })}>
                                                        Reject
                                                    </Button>
                                                </Stack>
                                            </Stack>
                                        </Box>
                                    ))
                                ) : (
                                    <EmptyState icon={<ReviewIcon />} title="No reviews queued" description="Review requests created from runs will appear here." />
                                )}
                            </Stack>

                            <Stack spacing={1.5}>
                                <Typography variant="subtitle2">Evaluation datasets</Typography>
                                <TextField label="Dataset name" value={datasetForm.name} onChange={(event) => setDatasetForm((current) => ({ ...current, name: event.target.value }))} fullWidth />
                                <TextField label="Dataset description" value={datasetForm.description} onChange={(event) => setDatasetForm((current) => ({ ...current, description: event.target.value }))} fullWidth />
                                <Button variant="outlined" disabled={createDatasetMutation.isPending || !datasetForm.name.trim()} onClick={() => createDatasetMutation.mutate(datasetForm)}>
                                    {createDatasetMutation.isPending ? "Creating..." : "Create evaluation dataset"}
                                </Button>
                                <TextField select label="Selected dataset" value={selectedDatasetId} onChange={(event) => setSelectedDatasetId(event.target.value)} fullWidth>
                                    {datasets.map((dataset) => (
                                        <MenuItem key={dataset.id} value={dataset.id}>
                                            {dataset.name}
                                        </MenuItem>
                                    ))}
                                </TextField>
                                <TextField label="Case input variables JSON" value={datasetCaseForm.input_variables_json} onChange={(event) => setDatasetCaseForm((current) => ({ ...current, input_variables_json: event.target.value }))} fullWidth multiline minRows={4} />
                                <TextField label="Expected output text" value={datasetCaseForm.expected_output_text} onChange={(event) => setDatasetCaseForm((current) => ({ ...current, expected_output_text: event.target.value }))} fullWidth multiline minRows={2} />
                                <TextField label="Expected output JSON" value={datasetCaseForm.expected_output_json} onChange={(event) => setDatasetCaseForm((current) => ({ ...current, expected_output_json: event.target.value }))} fullWidth multiline minRows={2} />
                                <TextField label="Notes" value={datasetCaseForm.notes} onChange={(event) => setDatasetCaseForm((current) => ({ ...current, notes: event.target.value }))} fullWidth />
                                <Button
                                    variant="outlined"
                                    disabled={createDatasetCaseMutation.isPending || !selectedDatasetId}
                                    onClick={() => {
                                        try {
                                            createDatasetCaseMutation.mutate({
                                                datasetId: selectedDatasetId,
                                                payload: {
                                                    input_variables: parseJsonObject(datasetCaseForm.input_variables_json),
                                                    expected_output_text: datasetCaseForm.expected_output_text || null,
                                                    expected_output_json: datasetCaseForm.expected_output_json.trim()
                                                        ? parseJsonObject(datasetCaseForm.expected_output_json)
                                                        : null,
                                                    notes: datasetCaseForm.notes || null,
                                                },
                                            });
                                        } catch (error) {
                                            showToast({
                                                message: error instanceof Error ? error.message : "Invalid dataset case JSON.",
                                                severity: "error",
                                            });
                                        }
                                    }}
                                >
                                    {createDatasetCaseMutation.isPending ? "Saving..." : "Add dataset case"}
                                </Button>
                                <TextField
                                    select
                                    label="Prompt version for evaluation"
                                    value={runForm.prompt_version_id}
                                    onChange={(event) => setRunForm((current) => ({ ...current, prompt_version_id: event.target.value }))}
                                    fullWidth
                                >
                                    {selectedTemplateVersions.map((version) => (
                                        <MenuItem key={version.id} value={version.id}>
                                            v{version.version_number} • {version.model_name}
                                        </MenuItem>
                                    ))}
                                </TextField>
                                <Button
                                    variant="contained"
                                    disabled={runEvaluationMutation.isPending || !selectedDatasetId || !runForm.prompt_version_id}
                                    onClick={() => runEvaluationMutation.mutate({ datasetId: selectedDatasetId, promptVersionId: runForm.prompt_version_id })}
                                >
                                    {runEvaluationMutation.isPending ? "Evaluating..." : "Run evaluation"}
                                </Button>
                                {selectedDatasetCases.length > 0 && (
                                    <Stack spacing={1}>
                                        {selectedDatasetCases.map((item) => (
                                            <Box key={item.id} sx={(theme) => ({ p: 1.5, borderRadius: 3, border: `1px solid ${theme.palette.divider}` })}>
                                                <Typography variant="body2" sx={{ fontFamily: '"IBM Plex Mono", monospace' }}>
                                                    {JSON.stringify(item.input_variables)}
                                                </Typography>
                                                {item.expected_output_text && (
                                                    <Typography variant="caption" color="text.secondary">
                                                        Expected: {item.expected_output_text}
                                                    </Typography>
                                                )}
                                            </Box>
                                        ))}
                                    </Stack>
                                )}
                                {evaluationRuns.length > 0 && (
                                    <Stack spacing={1}>
                                        {evaluationRuns.map((run) => (
                                            <Alert key={run.id} severity={run.passed_cases === run.total_cases ? "success" : "warning"}>
                                                {formatDateTime(run.created_at)}: {run.passed_cases}/{run.total_cases} passed, average score {run.average_score}
                                            </Alert>
                                        ))}
                                    </Stack>
                                )}
                            </Stack>
                        </Stack>
                    </SectionCard>
                </Stack>
            </Box>
        </PageShell>
    );
}
