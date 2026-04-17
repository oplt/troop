import { Stack } from "@mui/material";

import type { Agent } from "../../api/orchestration";
import { AgentRegistryPanel } from "./AgentRegistryPanel";

type MyTemplatesViewProps = {
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

export function MyTemplatesView(props: MyTemplatesViewProps) {
    return (
        <Stack spacing={2}>
            <AgentRegistryPanel {...props} />
        </Stack>
    );
}
