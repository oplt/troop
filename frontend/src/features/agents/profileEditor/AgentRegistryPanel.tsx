import { Add as AddIcon, SmartToy as AgentIcon } from "@mui/icons-material";
import { Box, Button, Paper, Stack, Typography } from "@mui/material";
import { Link as RouterLink } from "react-router-dom";

import type { Agent, AgentTemplate } from "../../../api/orchestration";
import { EmptyState } from "../../../components/ui/EmptyState";
import { StatusChip } from "../../../components/ui/StatusChip";

type AgentRegistryPanelProps = {
    agents: Agent[];
    filteredAgents: Agent[];
    templates: AgentTemplate[];
    selectedAgentId: string | null | undefined;
    isCreatingFromTemplate: boolean;
    onSelectAgent: (agentId: string) => void;
    onNewDraft: () => void;
    onCreateFromTemplate: (template: AgentTemplate) => void;
};

export function AgentRegistryPanel({
    agents,
    filteredAgents,
    templates,
    selectedAgentId,
    isCreatingFromTemplate,
    onSelectAgent,
    onNewDraft,
    onCreateFromTemplate,
}: AgentRegistryPanelProps) {
    return (
        <Stack spacing={2}>
            <Paper sx={{ p: 2, borderRadius: 1 }}>
                <Typography variant="subtitle1">Registry</Typography>
                <Typography variant="caption" color="text.secondary">
                    {filteredAgents.length} profiles in this scope
                </Typography>
                <Stack spacing={1} sx={{ mt: 1.5 }}>
                    {filteredAgents.map((item) => (
                        <Button
                            key={item.id}
                            variant={selectedAgentId === item.id ? "contained" : "outlined"}
                            onClick={() => onSelectAgent(item.id)}
                            sx={{ justifyContent: "flex-start", textAlign: "left" }}
                        >
                            <Box>
                                <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                                    <Typography variant="body2">{item.name}</Typography>
                                    <StatusChip
                                        status={item.is_active ? "active" : "draft"}
                                        kind="project"
                                        size="small"
                                        showIcon={false}
                                    />
                                </Stack>
                                <Typography variant="caption">
                                    {item.role} · v{item.version}
                                </Typography>
                            </Box>
                        </Button>
                    ))}
                    {filteredAgents.length === 0 &&
                        (agents.length === 0 ? (
                            <EmptyState
                                icon={<AgentIcon />}
                                title="No agents in this scope"
                                description="Create a draft contract or install a validated template to start the registry."
                                action={
                                    <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                                        <Button
                                            size="small"
                                            variant="contained"
                                            startIcon={<AddIcon />}
                                            onClick={onNewDraft}
                                        >
                                            New draft
                                        </Button>
                                        {templates[0] ? (
                                            <Button
                                                size="small"
                                                variant="outlined"
                                                disabled={isCreatingFromTemplate}
                                                onClick={() => onCreateFromTemplate(templates[0])}
                                            >
                                                Use template
                                            </Button>
                                        ) : (
                                            <Button
                                                size="small"
                                                variant="outlined"
                                                component={RouterLink}
                                                to="/marketplace"
                                            >
                                                Browse Marketplace
                                            </Button>
                                        )}
                                    </Stack>
                                }
                            />
                        ) : (
                            <Typography color="text.secondary">No agents match the current filters.</Typography>
                        ))}
                </Stack>
            </Paper>

            <Paper sx={{ p: 2, borderRadius: 1 }}>
                <Typography variant="subtitle1">Templates</Typography>
                <Typography variant="caption" color="text.secondary">
                    Validated starting points with inheritance and skill composition.
                </Typography>
                <Stack spacing={1} sx={{ mt: 1.5 }}>
                    {templates.map((item) => (
                        <Button
                            key={item.slug}
                            size="small"
                            variant="outlined"
                            disabled={isCreatingFromTemplate}
                            onClick={() => onCreateFromTemplate(item)}
                            sx={{ justifyContent: "space-between", textTransform: "none" }}
                        >
                            <span>{item.name}</span>
                            <Typography variant="caption">{item.role}</Typography>
                        </Button>
                    ))}
                </Stack>
            </Paper>
        </Stack>
    );
}
