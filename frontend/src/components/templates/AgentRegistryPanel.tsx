import { Alert, Button, Chip, Paper, Stack, Switch, Typography } from "@mui/material";
import { SmartToy as AgentIcon } from "@mui/icons-material";

import type { Agent } from "../../api/orchestration";
import { EmptyState } from "../ui/EmptyState";
import { TemplateSection } from "./TemplateSection";

type AgentRegistryPanelProps = {
    agents: Agent[];
    isLoadingAgents: boolean;
    agentLiveStatus: Map<string, "running" | "blocked" | "queued" | "idle">;
    simulationAgentId: string | null;
    isSimulatingAgent: boolean;
    getSkillDisplayName: (slug: string) => string;
    onDuplicateAgent: (agentId: string) => void;
    onToggleAgent: (payload: { agentId: string; active: boolean }) => void;
    onOpenVersions: (agent: Agent) => void;
    onOpenTestRun: (agent: Agent) => void;
    onSimulateAgent: (agentId: string) => void;
};

export function AgentRegistryPanel({
    agents,
    isLoadingAgents,
    agentLiveStatus,
    simulationAgentId,
    isSimulatingAgent,
    getSkillDisplayName,
    onDuplicateAgent,
    onToggleAgent,
    onOpenVersions,
    onOpenTestRun,
    onSimulateAgent,
}: AgentRegistryPanelProps) {
    return (
        <TemplateSection title="Agent registry" description="Current saved agents, live state, version/test actions.">
            {isLoadingAgents ? (
                <Typography color="text.secondary">Loading agents...</Typography>
            ) : agents.length === 0 ? (
                <EmptyState icon={<AgentIcon fontSize="small" />} title="No agents yet" description="Build from template or create from scratch." />
            ) : (
                <Stack spacing={1.5}>
                    {agents.map((agent) => (
                        <Paper key={agent.id} sx={{ p: 2, borderRadius: 4 }}>
                            <Stack spacing={1.25}>
                                <Stack direction={{ xs: "column", md: "row" }} justifyContent="space-between" spacing={1}>
                                    <div>
                                        <Typography variant="subtitle1">{agent.name}</Typography>
                                        <Typography variant="body2" color="text.secondary">
                                            {agent.role} • {agent.slug}
                                            {agent.parent_template_slug ? ` • template ${agent.parent_template_slug}` : ""}
                                        </Typography>
                                    </div>
                                    <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                                        <Chip label={agentLiveStatus.get(agent.id) ?? "idle"} size="small" variant="outlined" />
                                        <Switch
                                            checked={agent.is_active}
                                            onChange={(_, checked) => onToggleAgent({ agentId: agent.id, active: checked })}
                                        />
                                        <Button size="small" onClick={() => onDuplicateAgent(agent.id)}>
                                            Duplicate
                                        </Button>
                                        <Button size="small" variant="outlined" onClick={() => onOpenVersions(agent)}>
                                            Versions
                                        </Button>
                                        <Button size="small" variant="contained" onClick={() => onOpenTestRun(agent)}>
                                            Test run
                                        </Button>
                                        <Button
                                            size="small"
                                            variant="outlined"
                                            onClick={() => onSimulateAgent(agent.id)}
                                            disabled={isSimulatingAgent}
                                        >
                                            Simulate
                                        </Button>
                                    </Stack>
                                </Stack>
                                <Typography variant="body2" color="text.secondary">
                                    {agent.description || "No description provided."}
                                </Typography>
                                <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
                                    {agent.skills.map((item) => (
                                        <Chip key={`${agent.id}-${item}`} label={getSkillDisplayName(item)} size="small" color="info" variant="outlined" />
                                    ))}
                                    {(agent.inheritance?.effective.capabilities || agent.capabilities).map((item) => (
                                        <Chip key={`${agent.id}-cap-${item}`} label={item} size="small" variant="outlined" />
                                    ))}
                                </Stack>
                                {agent.lint?.warnings.length ? (
                                    <Alert severity="warning">{agent.lint.warnings.slice(0, 3).join(" ")}</Alert>
                                ) : null}
                                {agent.lint?.errors.length ? (
                                    <Alert severity="error">{agent.lint.errors.join(" ")}</Alert>
                                ) : null}
                                {simulationAgentId === agent.id && (
                                    <Alert severity="info">Simulation queued for {agent.name}.</Alert>
                                )}
                            </Stack>
                        </Paper>
                    ))}
                </Stack>
            )}
        </TemplateSection>
    );
}
