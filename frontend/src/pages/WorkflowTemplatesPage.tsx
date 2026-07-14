import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Box, Button, Chip, MenuItem, Paper, Stack, TextField, Typography } from "@mui/material";
import { AccountTree as WorkflowIcon, CheckCircle as AppliedIcon } from "@mui/icons-material";

import {
    applyWorkflowTemplate,
    listCustomWorkflowTemplates,
    listOrchestrationProjects,
    listWorkflowTemplates,
    saveCustomWorkflowTemplate,
    type WorkflowTemplate,
} from "../api/orchestration";
import { queryKeys } from "../config/queryKeys";
import { useSnackbar } from "../app/snackbarContext";
import { extractApiErrorMessage } from "../utils/apiErrors";
import { PageShell } from "../components/ui/PageShell";
import { SectionCard } from "../components/ui/SectionCard";

export default function WorkflowTemplatesPage() {
    const queryClient = useQueryClient();
    const { showToast } = useSnackbar();
    const [projectId, setProjectId] = useState("");
    const [customName, setCustomName] = useState("");
    const [customStages, setCustomStages] = useState("plan\nimplement\nreview\nship");
    const { data: projects = [] } = useQuery({
        queryKey: queryKeys.orchestration.projects,
        queryFn: listOrchestrationProjects,
    });
    const { data: templates = [], isLoading: templatesLoading } = useQuery({
        queryKey: queryKeys.orchestration.workflowTemplates,
        queryFn: listWorkflowTemplates,
    });
    const { data: customTemplates = [] } = useQuery({
        queryKey: queryKeys.orchestration.projectWorkflowTemplates(projectId),
        queryFn: () => listCustomWorkflowTemplates(projectId),
        enabled: Boolean(projectId),
    });

    useEffect(() => {
        if (!projectId && projects[0]?.id) setProjectId(projects[0].id);
    }, [projectId, projects]);

    const applyMutation = useMutation({
        mutationFn: (templateId: string) => applyWorkflowTemplate(projectId, templateId),
        onSuccess: async (result) => {
            await queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.project(projectId) });
            showToast({ message: `Applied ${result.template.name} to the project.`, severity: "success" });
        },
        onError: (error) => showToast({ message: extractApiErrorMessage(error, "Could not apply workflow template."), severity: "error" }),
    });
    const saveMutation = useMutation({
        mutationFn: () => saveCustomWorkflowTemplate(projectId, {
            name: customName.trim(),
            stages: customStages.split("\n").map((stage) => stage.trim()).filter(Boolean).map((title) => ({ title })),
        }),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.projectWorkflowTemplates(projectId) });
            setCustomName("");
            showToast({ message: "Custom workflow template saved.", severity: "success" });
        },
        onError: (error) => showToast({ message: extractApiErrorMessage(error, "Could not save custom workflow."), severity: "error" }),
    });

    const renderTemplate = (template: WorkflowTemplate, applyId = template.id) => (
        <Paper key={applyId} variant="outlined" sx={{ p: 2, borderRadius: 1 }}>
            <Stack direction={{ xs: "column", md: "row" }} justifyContent="space-between" spacing={2}>
                <Box sx={{ flex: 1 }}>
                    <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                        <Typography variant="subtitle1">{template.name}</Typography>
                        <Chip size="small" variant="outlined" label={template.id} />
                    </Stack>
                    <Typography variant="body2" color="text.secondary" sx={{ mt: 0.75 }}>{template.description}</Typography>
                    <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap sx={{ mt: 1 }}>
                        {Object.entries(template.suggested_execution).map(([key, value]) => <Chip key={key} size="small" label={`${key}: ${String(value)}`} />)}
                    </Stack>
                </Box>
                <Button
                    variant="contained"
                    startIcon={applyMutation.isPending && applyMutation.variables === applyId ? <AppliedIcon /> : <WorkflowIcon />}
                    disabled={!projectId || applyMutation.isPending}
                    onClick={() => applyMutation.mutate(applyId)}
                >
                    Apply
                </Button>
            </Stack>
        </Paper>
    );

    return (
        <PageShell>
            <Stack direction={{ xs: "column", md: "row" }} justifyContent="space-between" spacing={2}>
                <Box>
                    <Typography variant="overline" color="text.secondary">Orchestration</Typography>
                    <Typography variant="h3">Workflow templates</Typography>
                    <Typography color="text.secondary" sx={{ mt: 1 }}>Apply repeatable operating modes to a project, then tailor the resulting execution settings.</Typography>
                </Box>
                <TextField select label="Target project" value={projectId} onChange={(event) => setProjectId(event.target.value)} sx={{ minWidth: { md: 280 } }}>
                    {projects.map((project) => <MenuItem key={project.id} value={project.id}>{project.name}</MenuItem>)}
                </TextField>
            </Stack>

            {!projectId ? <Alert severity="info">Create or select a project to apply a workflow.</Alert> : null}
            <SectionCard title="Built-in workflows" description="Curated v2 defaults for feature delivery, incidents, security, and documentation.">
                {templatesLoading ? <Typography color="text.secondary">Loading templates…</Typography> : <Stack spacing={1.5}>{templates.map((template) => renderTemplate(template))}</Stack>}
            </SectionCard>
            <SectionCard title="Custom project workflow" description="Save a project-specific stage sequence for reuse. Stages are stored as an ordered, auditable workflow definition.">
                <Stack spacing={2}>
                    <TextField label="Workflow name" value={customName} onChange={(event) => setCustomName(event.target.value)} placeholder="Release readiness" fullWidth />
                    <TextField label="Stages" value={customStages} onChange={(event) => setCustomStages(event.target.value)} helperText="One stage per line." multiline minRows={4} fullWidth />
                    <Button variant="outlined" disabled={!projectId || !customName.trim() || !customStages.trim() || saveMutation.isPending} onClick={() => saveMutation.mutate()}>Save custom workflow</Button>
                    {customTemplates.length > 0 ? <Stack spacing={1}>{customTemplates.map((item) => renderTemplate({ id: `custom:${String(item.id)}`, name: String(item.name ?? "Custom workflow"), description: String(item.description ?? "Custom project workflow"), suggested_execution: (item.suggested_execution as Record<string, unknown>) ?? {} }, `custom:${String(item.id)}`))}</Stack> : <Typography variant="body2" color="text.secondary">No custom workflows saved for this project.</Typography>}
                </Stack>
            </SectionCard>
        </PageShell>
    );
}
