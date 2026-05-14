import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
    Alert,
    Box,
    Button,
    Chip,
    Divider,
    MenuItem,
    Paper,
    Stack,
    TextField,
    Typography,
} from "@mui/material";
import { Add as AddIcon, UploadFile as UploadFileIcon } from "@mui/icons-material";
import {
    createAgent,
    importAgentMarkdown,
    listAgents,
    listOrchestrationProjects,
    listTools,
    updateAgent,
    type Agent,
} from "../api/orchestration";
import { PageShell } from "../components/ui/PageShell";

const DEFAULT_MARKDOWN = `---
name: Irrigation Analyst
role: agriculture_imagery_specialist
tools_allowed:
  - file_read_stub
  - geospatial_analysis_stub
model:
  provider: openai
  model: gpt-4.1
---

Inspect project imagery, summarize irrigation anomalies, and propose next field checks.`;

function modelLabel(agent: Agent) {
    const provider = typeof agent.model_policy.provider === "string" ? agent.model_policy.provider : "provider";
    const model = typeof agent.model_policy.model === "string" ? agent.model_policy.model : "model";
    return `${provider} / ${model}`;
}

export default function AgentProfilesPage() {
    const queryClient = useQueryClient();
    const [selectedProjectId, setSelectedProjectId] = useState("");
    const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
    const [markdown, setMarkdown] = useState(DEFAULT_MARKDOWN);
    const [error, setError] = useState("");

    const { data: projects = [] } = useQuery({
        queryKey: ["orchestration", "projects"],
        queryFn: listOrchestrationProjects,
    });
    const { data: agents = [] } = useQuery({
        queryKey: ["agents", selectedProjectId || "global"],
        queryFn: () => listAgents(selectedProjectId || undefined),
    });
    const { data: tools = [] } = useQuery({
        queryKey: ["tools"],
        queryFn: listTools,
    });

    const selectedAgent = useMemo(
        () => agents.find((agent) => agent.id === selectedAgentId) ?? agents[0] ?? null,
        [agents, selectedAgentId],
    );

    const saveMutation = useMutation({
        mutationFn: async () => {
            setError("");
            if (selectedAgent) {
                const source = markdown.trim() ? markdown : selectedAgent.source_markdown;
                return updateAgent(selectedAgent.id, { source_markdown: source });
            }
            const file = new File([markdown], "agent.md", { type: "text/markdown" });
            return importAgentMarkdown(file, selectedProjectId || undefined);
        },
        onSuccess: (agent) => {
            setSelectedAgentId(agent.id);
            void queryClient.invalidateQueries({ queryKey: ["agents"] });
        },
        onError: (err) => setError(err instanceof Error ? err.message : "Agent save failed."),
    });

    const quickCreateMutation = useMutation({
        mutationFn: () =>
            createAgent({
                name: "New Specialist",
                slug: `new-specialist-${Date.now()}`,
                role: "specialist",
                project_id: selectedProjectId || null,
                system_prompt: "Assist with project tasks using approved tools only.",
                allowed_tools: ["file_read_stub"],
                model_policy: { provider: "openai", model: "gpt-4.1" },
            }),
        onSuccess: (agent) => {
            setSelectedAgentId(agent.id);
            setMarkdown(agent.source_markdown || DEFAULT_MARKDOWN);
            void queryClient.invalidateQueries({ queryKey: ["agents"] });
        },
    });

    return (
        <PageShell maxWidth="xl">
            <Paper sx={{ p: { xs: 2.5, md: 3 }, borderRadius: 2 }}>
                <Stack direction={{ xs: "column", md: "row" }} justifyContent="space-between" spacing={2}>
                    <Box>
                        <Typography variant="overline" color="text.secondary">
                            Agent profiles
                        </Typography>
                        <Typography variant="h3">Markdown-defined collaborators</Typography>
                        <Typography color="text.secondary" sx={{ mt: 1, maxWidth: 720 }}>
                            Import or edit agent instructions, allowed tools, and model routing without changing project flows.
                        </Typography>
                    </Box>
                    <Stack direction={{ xs: "column", sm: "row" }} spacing={1} alignItems={{ sm: "center" }}>
                        <TextField
                            select
                            label="Project"
                            value={selectedProjectId}
                            onChange={(event) => {
                                setSelectedProjectId(event.target.value);
                                setSelectedAgentId(null);
                            }}
                            sx={{ minWidth: 240 }}
                        >
                            <MenuItem value="">Global agents</MenuItem>
                            {projects.map((project) => (
                                <MenuItem key={project.id} value={project.id}>
                                    {project.name}
                                </MenuItem>
                            ))}
                        </TextField>
                        <Button
                            variant="outlined"
                            startIcon={<AddIcon />}
                            onClick={() => quickCreateMutation.mutate()}
                            disabled={quickCreateMutation.isPending}
                        >
                            Create
                        </Button>
                    </Stack>
                </Stack>
            </Paper>

            {error && <Alert severity="error">{error}</Alert>}

            <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", lg: "360px 1fr" }, gap: 3 }}>
                <Paper sx={{ p: 2, borderRadius: 2 }}>
                    <Stack spacing={1.5}>
                        {agents.map((agent) => (
                            <Button
                                key={agent.id}
                                variant={selectedAgent?.id === agent.id ? "contained" : "outlined"}
                                onClick={() => {
                                    setSelectedAgentId(agent.id);
                                    setMarkdown(agent.source_markdown || DEFAULT_MARKDOWN);
                                }}
                                sx={{ justifyContent: "flex-start", textAlign: "left" }}
                            >
                                {agent.name}
                            </Button>
                        ))}
                        {agents.length === 0 && (
                            <Typography color="text.secondary">No agents in this scope.</Typography>
                        )}
                    </Stack>
                </Paper>

                <Paper sx={{ p: { xs: 2, md: 3 }, borderRadius: 2 }}>
                    <Stack spacing={2.5}>
                        {selectedAgent && (
                            <Box>
                                <Typography variant="h5">{selectedAgent.name}</Typography>
                                <Typography color="text.secondary">{selectedAgent.role} · {modelLabel(selectedAgent)}</Typography>
                                <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" sx={{ mt: 1.5 }}>
                                    {selectedAgent.allowed_tools.map((tool) => (
                                        <Chip key={tool} label={tool} size="small" />
                                    ))}
                                </Stack>
                            </Box>
                        )}

                        <TextField
                            label="Markdown profile"
                            value={markdown}
                            onChange={(event) => setMarkdown(event.target.value)}
                            multiline
                            minRows={16}
                            fullWidth
                        />
                        <Button
                            variant="contained"
                            startIcon={<UploadFileIcon />}
                            disabled={saveMutation.isPending}
                            onClick={() => saveMutation.mutate()}
                        >
                            {selectedAgent ? "Update from Markdown" : "Import Markdown"}
                        </Button>

                        <Divider />
                        <Box>
                            <Typography variant="h6">Available tools</Typography>
                            <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" sx={{ mt: 1.5 }}>
                                {tools.map((tool) => (
                                    <Chip
                                        key={tool.name}
                                        label={`${tool.name} · ${tool.risk_level}${tool.requires_approval ? " · approval" : ""}`}
                                        color={tool.risk_level === "high" ? "error" : tool.risk_level === "medium" ? "warning" : "default"}
                                        variant="outlined"
                                    />
                                ))}
                            </Stack>
                        </Box>
                    </Stack>
                </Paper>
            </Box>
        </PageShell>
    );
}
