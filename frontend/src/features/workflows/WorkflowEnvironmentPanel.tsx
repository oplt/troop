import {
    Alert,
    Box,
    Button,
    Chip,
    CircularProgress,
    Divider,
    MenuItem,
    Stack,
    TextField,
    Typography,
} from "@mui/material";
import { RocketLaunch, Undo } from "@mui/icons-material";
import type {
    WorkflowEnvironmentDiffResponse,
    WorkflowEnvironmentHistoryEvent,
    WorkflowEnvironmentSummary,
    WorkflowVersionSummary,
} from "../../api/workforce";
import { formatDateTime, humanizeKey } from "../../utils/formatters";

const ENVIRONMENTS = ["dev", "staging", "prod"] as const;

type WorkflowEnvironmentPanelProps = {
    workflowId: string | null;
    selectedEnvironment: string;
    onEnvironmentChange: (environment: string) => void;
    environments: WorkflowEnvironmentSummary[] | undefined;
    environmentsLoading: boolean;
    versions: WorkflowVersionSummary[];
    promoteVersionId: string;
    onPromoteVersionChange: (versionId: string) => void;
    envDiff: WorkflowEnvironmentDiffResponse | null;
    envDiffLoading: boolean;
    history: WorkflowEnvironmentHistoryEvent[] | undefined;
    onPromote: () => void;
    onRollback: () => void;
    promotePending: boolean;
    rollbackPending: boolean;
};

export function WorkflowEnvironmentPanel({
    workflowId,
    selectedEnvironment,
    onEnvironmentChange,
    environments,
    environmentsLoading,
    versions,
    promoteVersionId,
    onPromoteVersionChange,
    envDiff,
    envDiffLoading,
    history,
    onPromote,
    onRollback,
    promotePending,
    rollbackPending,
}: WorkflowEnvironmentPanelProps) {
    if (!workflowId) {
        return <Alert severity="info">Save a draft before managing environment deployments.</Alert>;
    }

    const active = environments?.find((item) => item.environment === selectedEnvironment);

    return (
        <Stack spacing={2}>
            <TextField
                select
                label="Environment"
                size="small"
                value={selectedEnvironment}
                onChange={(event) => onEnvironmentChange(event.target.value)}
                fullWidth
            >
                {ENVIRONMENTS.map((env) => (
                    <MenuItem key={env} value={env}>{humanizeKey(env)}</MenuItem>
                ))}
            </TextField>

            {environmentsLoading ? (
                <CircularProgress size={20} />
            ) : (
                <Alert severity={active?.deployed ? "success" : "info"}>
                    {active?.deployed
                        ? `${humanizeKey(selectedEnvironment)} runs version v${active.version_number ?? "?"}`
                        : `No deployment in ${humanizeKey(selectedEnvironment)} yet.`}
                </Alert>
            )}

            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                <TextField
                    select
                    label="Promote version"
                    size="small"
                    value={promoteVersionId}
                    onChange={(event) => onPromoteVersionChange(event.target.value)}
                    sx={{ minWidth: 180, flex: 1 }}
                >
                    <MenuItem value="">Select version</MenuItem>
                    {versions.map((version) => (
                        <MenuItem key={version.id} value={version.id}>
                            v{version.version_number}
                        </MenuItem>
                    ))}
                </TextField>
                <Button
                    variant="contained"
                    startIcon={<RocketLaunch />}
                    onClick={onPromote}
                    disabled={!promoteVersionId || promotePending}
                >
                    Promote
                </Button>
                <Button
                    variant="outlined"
                    startIcon={<Undo />}
                    onClick={onRollback}
                    disabled={!active?.deployed || rollbackPending}
                >
                    Rollback
                </Button>
            </Stack>

            <Box>
                <Typography variant="subtitle2" gutterBottom>
                    Promotion diff
                </Typography>
                {envDiffLoading ? (
                    <CircularProgress size={20} />
                ) : envDiff ? (
                    <Stack spacing={1}>
                        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                            <Chip size="small" label={`+${envDiff.summary.nodes_added ?? 0} nodes`} />
                            <Chip size="small" label={`~${envDiff.bindings_changed_count ?? 0} binding changes`} />
                            <Chip
                                size="small"
                                color={envDiff.graph_changed || (envDiff.bindings_changed_count ?? 0) > 0 ? "warning" : "success"}
                                label={envDiff.graph_changed || (envDiff.bindings_changed_count ?? 0) > 0 ? "Changes detected" : "No changes"}
                            />
                        </Stack>
                        {envDiff.bindings_changed.length > 0 && (
                            <Typography variant="caption" color="text.secondary">
                                Binding changes: {envDiff.bindings_changed.map((item) => item.node_id).join(", ")}
                            </Typography>
                        )}
                    </Stack>
                ) : (
                    <Typography variant="body2" color="text.secondary">
                        Select a version to preview graph and binding changes.
                    </Typography>
                )}
            </Box>

            <Divider />

            <Box>
                <Typography variant="subtitle2" gutterBottom>
                    Deployment history
                </Typography>
                {!history?.length ? (
                    <Typography variant="body2" color="text.secondary">No promotions yet.</Typography>
                ) : (
                    <Stack spacing={1}>
                        {history.map((event) => (
                            <Stack
                                key={event.id}
                                sx={{ p: 1.25, border: 1, borderColor: "divider", borderRadius: 1 }}
                                spacing={0.5}
                            >
                                <Typography variant="subtitle2">
                                    {humanizeKey(event.action)} · v{versions.find((v) => v.id === event.workflow_version_id)?.version_number ?? "?"}
                                </Typography>
                                <Typography variant="caption" color="text.secondary">
                                    {formatDateTime(event.created_at)}
                                </Typography>
                            </Stack>
                        ))}
                    </Stack>
                )}
            </Box>

            {selectedEnvironment === "prod" && (
                <Alert severity="warning">
                    Production deployments require prod-tagged connector installations. Dev credentials are rejected at promote time.
                </Alert>
            )}
        </Stack>
    );
}

export { ENVIRONMENTS as WORKFLOW_ENVIRONMENTS };
