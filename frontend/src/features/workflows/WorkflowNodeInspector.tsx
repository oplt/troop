import {
    Alert,
    Button,
    MenuItem,
    Stack,
    TextField,
    Typography,
} from "@mui/material";
import { DeleteOutline } from "@mui/icons-material";
import { ConnectorOperationFields } from "../connectors/ConnectorSetupForm";
import { findManifestOperation, listManifestTriggers } from "../connectors/manifestUtils";
import type { ConnectorManifest } from "../../api/integrations";
import { humanizeKey } from "../../utils/formatters";
import {
    NODE_TYPE_DESCRIPTIONS,
    nodeConfigFor,
    type ToolNodeConfig,
    type TriggerNodeConfig,
} from "./nodeSchemas";
import type { WorkflowCanvasNode, WorkflowNodeType } from "./builderState";
import { WORKFLOW_NODE_TYPES } from "./builderState";

type WorkflowNodeInspectorProps = {
    node: WorkflowCanvasNode;
    installations: Array<{ id: string; name: string; status: string; providerSlug?: string }>;
    operations: Array<{ slug: string; name: string }>;
    manifests: ConnectorManifest[];
    agents: Array<{ id: string; name: string }>;
    skills: Array<{ id: string; name: string }>;
    workflows: Array<{ id: string; name: string }>;
    onChange: (node: WorkflowCanvasNode) => void;
    onDelete: () => void;
};

export function WorkflowNodeInspector({
    node,
    installations,
    operations,
    manifests,
    agents,
    skills,
    workflows,
    onChange,
    onDelete,
}: WorkflowNodeInspectorProps) {
    const config = node.data.config;
    const setConfig = (key: string, value: unknown) => onChange({
        ...node,
        data: { ...node.data, config: { ...config, [key]: value } },
    });

    const triggerConfig = nodeConfigFor("trigger", config) as TriggerNodeConfig;
    const toolConfig = nodeConfigFor("tool", config) as ToolNodeConfig;
    const params = (toolConfig.params && typeof toolConfig.params === "object" ? toolConfig.params : {}) as Record<string, unknown>;
    const operationSlug = String(toolConfig.tool_slug ?? toolConfig.operation ?? toolConfig.tool ?? "");
    const selectedInstallation = installations.find((item) => item.id === String(config.connector_installation_id ?? ""));
    const providerManifest = manifests.find((item) => item.provider_slug === selectedInstallation?.providerSlug);
    const operationManifest = manifests.find((item) => Boolean(findManifestOperation(item, operationSlug)));

    const triggerOptions = manifests.flatMap((manifest) =>
        listManifestTriggers(manifest).map((trigger) => ({
            value: trigger.slug === "gmail.new_message" ? "gmail_new_message" : trigger.slug,
            label: `${manifest.name} · ${trigger.name}`,
        })),
    );

    const setParam = (key: string, value: unknown) => setConfig("params", { ...params, [key]: value });
    const setOperation = (slug: string) => onChange({
        ...node,
        data: {
            ...node.data,
            config: {
                ...config,
                operation: slug,
                tool_slug: slug,
                tool: slug,
                params: {},
            },
        },
    });

    const commonConnection = ["trigger", "tool"].includes(node.data.nodeType);

    return (
        <Stack spacing={2}>
            <Stack direction="row" justifyContent="space-between" alignItems="center">
                <Typography variant="h6">Node configuration</Typography>
                <Button color="error" size="small" startIcon={<DeleteOutline />} onClick={onDelete}>Delete</Button>
            </Stack>
            <Typography variant="body2" color="text.secondary">
                {NODE_TYPE_DESCRIPTIONS[node.data.nodeType]}
            </Typography>
            <TextField
                label="Label"
                value={node.data.label}
                onChange={(event) => onChange({ ...node, data: { ...node.data, label: event.target.value } })}
                fullWidth
                size="small"
            />
            <TextField
                select
                label="Node type"
                value={node.data.nodeType}
                onChange={(event) => onChange({
                    ...node,
                    data: { ...node.data, nodeType: event.target.value as WorkflowNodeType, config: {} },
                })}
                fullWidth
                size="small"
            >
                {WORKFLOW_NODE_TYPES.map((type) => <MenuItem key={type} value={type}>{humanizeKey(type)}</MenuItem>)}
            </TextField>
            {commonConnection && (
                <TextField
                    select
                    required
                    label="Connection"
                    value={String(config.connector_installation_id ?? "")}
                    onChange={(event) => setConfig("connector_installation_id", event.target.value)}
                    helperText="External actions fail closed without an explicit connector_installation_id."
                    fullWidth
                    size="small"
                >
                    <MenuItem value="">Select a connection</MenuItem>
                    {installations.map((item) => (
                        <MenuItem key={item.id} value={item.id}>{item.name} · {humanizeKey(item.status)}</MenuItem>
                    ))}
                </TextField>
            )}
            {node.data.nodeType === "trigger" && (
                <TextField
                    select
                    label="Event type"
                    value={String(triggerConfig.event_type ?? triggerConfig.trigger_type ?? "")}
                    onChange={(event) => {
                        setConfig("event_type", event.target.value);
                        setConfig("trigger_type", event.target.value);
                    }}
                    size="small"
                    fullWidth
                >
                    <MenuItem value="">Select trigger</MenuItem>
                    {triggerOptions.map((item) => (
                        <MenuItem key={item.value} value={item.value}>{item.label}</MenuItem>
                    ))}
                    <MenuItem value="manual">Manual</MenuItem>
                    <MenuItem value="schedule">Schedule</MenuItem>
                </TextField>
            )}
            {node.data.nodeType === "agent" && (
                <>
                    <TextField select label="Agent" value={String(config.agent_id ?? "")} onChange={(event) => setConfig("agent_id", event.target.value)} size="small" fullWidth>
                        <MenuItem value="">Runtime selection</MenuItem>
                        {agents.map((item) => <MenuItem key={item.id} value={item.id}>{item.name}</MenuItem>)}
                    </TextField>
                    <TextField select label="Skill" value={String(config.skill_id ?? config.skill ?? "")} onChange={(event) => setConfig("skill_id", event.target.value)} size="small" fullWidth>
                        <MenuItem value="">No fixed skill</MenuItem>
                        {skills.map((item) => <MenuItem key={item.id} value={item.id}>{item.name}</MenuItem>)}
                    </TextField>
                    <TextField label="Input mapping" value={String(config.input_mapping ?? "")} onChange={(event) => setConfig("input_mapping", event.target.value)} size="small" fullWidth />
                </>
            )}
            {node.data.nodeType === "skill" && (
                <TextField select label="Skill" value={String(config.skill_id ?? "")} onChange={(event) => setConfig("skill_id", event.target.value)} size="small" fullWidth>
                    <MenuItem value="">Select skill</MenuItem>
                    {skills.map((item) => <MenuItem key={item.id} value={item.id}>{item.name}</MenuItem>)}
                </TextField>
            )}
            {node.data.nodeType === "tool" && (
                <>
                    <TextField select label="Operation" value={operationSlug} onChange={(event) => setOperation(event.target.value)} size="small" fullWidth>
                        <MenuItem value="">Select operation</MenuItem>
                        {operations.map((item) => <MenuItem key={item.slug} value={item.slug}>{item.name || item.slug}</MenuItem>)}
                    </TextField>
                    <ConnectorOperationFields
                        manifest={operationManifest ?? providerManifest}
                        operationSlug={operationSlug}
                        values={params}
                        onChange={setParam}
                    />
                    <TextField label="Advanced argument mapping" value={String(config.argument_mapping ?? "")} onChange={(event) => setConfig("argument_mapping", event.target.value)} size="small" multiline minRows={2} fullWidth helperText="Optional JSONPath map merged over params at runtime." />
                </>
            )}
            {["condition", "router"].includes(node.data.nodeType) && (
                <TextField label="Expression / routing rules" value={String(config.expression ?? config.rules ?? "")} onChange={(event) => setConfig(node.data.nodeType === "condition" ? "expression" : "rules", event.target.value)} multiline minRows={3} size="small" fullWidth />
            )}
            {node.data.nodeType === "parallel" && (
                <TextField label="Completion policy" value={String(config.completion_policy ?? config.join_policy ?? "all")} onChange={(event) => setConfig("completion_policy", event.target.value)} helperText="Examples: all, any, quorum" size="small" fullWidth />
            )}
            {node.data.nodeType === "approval" && (
                <>
                    <TextField label="Action" required value={String(config.action ?? "")} onChange={(event) => setConfig("action", event.target.value)} size="small" fullWidth helperText="For email sending use gmail.send_draft." />
                    <TextField select label="Delivery channel" value={String(config.delivery_channel ?? "troop")} onChange={(event) => setConfig("delivery_channel", event.target.value)} size="small" fullWidth>
                        <MenuItem value="troop">Troop</MenuItem>
                        <MenuItem value="telegram">Telegram</MenuItem>
                    </TextField>
                    <TextField label="Approver IDs" value={String(config.approvers ?? "")} onChange={(event) => setConfig("approvers", event.target.value)} size="small" fullWidth helperText="Comma-separated IDs, or leave empty for policy resolution." />
                </>
            )}
            {node.data.nodeType === "human_input" && (
                <TextField label="Prompt" value={String(config.prompt ?? "")} onChange={(event) => setConfig("prompt", event.target.value)} multiline minRows={2} size="small" fullWidth />
            )}
            {node.data.nodeType === "delay" && (
                <TextField label="Delay seconds" type="number" value={Number(config.delay_seconds ?? 60)} onChange={(event) => setConfig("delay_seconds", Number(event.target.value))} size="small" fullWidth />
            )}
            {node.data.nodeType === "subworkflow" && (
                <TextField select label="Workflow" value={String(config.workflow_id ?? config.subworkflow_id ?? "")} onChange={(event) => setConfig("workflow_id", event.target.value)} size="small" fullWidth>
                    <MenuItem value="">Select workflow</MenuItem>
                    {workflows.map((item) => <MenuItem key={item.id} value={item.id}>{item.name}</MenuItem>)}
                </TextField>
            )}
            <Alert severity="info" sx={{ "& .MuiAlert-message": { overflow: "hidden" } }}>
                Node id: <code>{node.id}</code> · config is typed per node kind on save.
            </Alert>
        </Stack>
    );
}
