import {
    CheckCircleOutline,
    ContentCopy,
    PlayArrow,
    Publish,
    UploadFile,
} from "@mui/icons-material";
import { Box, Button, Divider, Paper, Stack, Tab, Tabs, Typography } from "@mui/material";

import type { Agent, AgentVersion, ToolSpec } from "../../../api/orchestration";
import { FormFieldStack } from "../../../components/ui/FormFieldStack";
import { Subsection } from "../../../components/ui/Subsection";
import { AgentCapabilitiesForm } from "./AgentCapabilitiesForm";
import { AgentIdentityForm } from "./AgentIdentityForm";
import { AgentMarkdownEditor } from "./AgentMarkdownEditor";
import { AgentMemoryBudgetForm } from "./AgentMemoryBudgetForm";
import { AgentModelPolicyForm } from "./AgentModelPolicyForm";
import { AgentToolsSelector } from "./AgentToolsSelector";
import { AgentValidationPanel } from "./AgentValidationPanel";
import { AgentVersionHistory } from "./AgentVersionHistory";
import type { AgentEditorTab, AgentProfileForm, AgentValidationState } from "./types";

type AgentEditorPanelProps = {
    agent: Agent | null;
    form: AgentProfileForm;
    markdown: string;
    tools: ToolSpec[];
    versions: AgentVersion[];
    activeTab: AgentEditorTab;
    validation: AgentValidationState | null;
    dryRun: string;
    isSaving: boolean;
    isValidating: boolean;
    isRunningDryRun: boolean;
    isDuplicating: boolean;
    isTogglingActive: boolean;
    onTabChange: (tab: AgentEditorTab) => void;
    onFormChange: <K extends keyof AgentProfileForm>(key: K, value: AgentProfileForm[K]) => void;
    onMarkdownChange: (value: string) => void;
    onDuplicate: () => void;
    onToggleActive: () => void;
    onDryRun: () => void;
    onValidate: () => void;
    onSave: () => void;
};

const TAB_INDEX: Record<AgentEditorTab, number> = {
    contract: 0,
    instructions: 1,
    versions: 2,
    validation: 3,
};

const INDEX_TAB: AgentEditorTab[] = ["contract", "instructions", "versions", "validation"];

export function AgentEditorPanel({
    agent,
    form,
    markdown,
    tools,
    versions,
    activeTab,
    validation,
    dryRun,
    isSaving,
    isValidating,
    isRunningDryRun,
    isDuplicating,
    isTogglingActive,
    onTabChange,
    onFormChange,
    onMarkdownChange,
    onDuplicate,
    onToggleActive,
    onDryRun,
    onValidate,
    onSave,
}: AgentEditorPanelProps) {
    return (
        <Paper sx={{ p: { xs: 2, md: 3 }, borderRadius: 1 }}>
            <Stack spacing={2}>
                <Stack direction={{ xs: "column", md: "row" }} justifyContent="space-between" spacing={1}>
                    <Box>
                        <Typography variant="h5">{agent?.name ?? "New agent contract"}</Typography>
                        {agent && (
                            <Typography color="text.secondary">
                                {agent.role} · {String(agent.model_policy.provider ?? "provider")} /{" "}
                                {String(agent.model_policy.model ?? "model not set")} · v{agent.version}
                            </Typography>
                        )}
                    </Box>
                    {agent && (
                        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                            <Button
                                size="small"
                                variant="outlined"
                                startIcon={<ContentCopy />}
                                onClick={onDuplicate}
                                disabled={isDuplicating}
                            >
                                Duplicate
                            </Button>
                            <Button
                                size="small"
                                variant={agent.is_active ? "outlined" : "contained"}
                                startIcon={agent.is_active ? <CheckCircleOutline /> : <Publish />}
                                onClick={onToggleActive}
                                disabled={isTogglingActive}
                            >
                                {agent.is_active ? "Deactivate" : "Activate"}
                            </Button>
                            <Button
                                size="small"
                                variant="outlined"
                                startIcon={<PlayArrow />}
                                onClick={onDryRun}
                                disabled={isRunningDryRun}
                            >
                                Dry run
                            </Button>
                        </Stack>
                    )}
                </Stack>

                <Tabs
                    value={TAB_INDEX[activeTab]}
                    onChange={(_, value) => onTabChange(INDEX_TAB[value] ?? "contract")}
                    variant="scrollable"
                >
                    <Tab label="Contract" />
                    <Tab label="Instructions" />
                    <Tab label={`Versions (${versions.length})`} />
                    <Tab label="Validation" />
                </Tabs>

                {activeTab === "contract" && (
                    <FormFieldStack>
                        <Subsection title="Identity">
                            <AgentIdentityForm form={form} onChange={onFormChange} />
                        </Subsection>
                        <AgentCapabilitiesForm form={form} onChange={onFormChange} />
                        <AgentToolsSelector form={form} tools={tools} onChange={onFormChange} />
                        <Divider />
                        <Subsection
                            title="Model policy"
                            info="These settings are passed to the provider router for every run of this agent."
                        >
                            <AgentModelPolicyForm form={form} onChange={onFormChange} />
                        </Subsection>
                        <Subsection title="Memory, budget, and output">
                            <AgentMemoryBudgetForm form={form} onChange={onFormChange} />
                        </Subsection>
                    </FormFieldStack>
                )}

                {activeTab === "instructions" && (
                    <AgentMarkdownEditor markdown={markdown} onChange={onMarkdownChange} />
                )}

                {activeTab === "versions" && <AgentVersionHistory versions={versions} />}

                {activeTab === "validation" && (
                    <AgentValidationPanel validation={validation} dryRun={dryRun} />
                )}

                <Divider />
                <Stack direction={{ xs: "column", sm: "row" }} spacing={1} justifyContent="flex-end">
                    <Button variant="outlined" onClick={onValidate} disabled={isValidating}>
                        {isValidating ? "Validating…" : "Validate contract"}
                    </Button>
                    <Button variant="contained" startIcon={<UploadFile />} onClick={onSave} disabled={isSaving}>
                        {isSaving ? "Saving…" : agent ? "Save new version" : "Register agent"}
                    </Button>
                </Stack>
            </Stack>
        </Paper>
    );
}
