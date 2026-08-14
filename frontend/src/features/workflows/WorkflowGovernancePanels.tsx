import {
    Alert,
    Box,
    Button,
    Chip,
    CircularProgress,
    Divider,
    Stack,
    TextField,
    Typography,
} from "@mui/material";
import { Science, PlayArrow } from "@mui/icons-material";
import type { WorkflowDiffResponse, WorkflowVersionSummary } from "../../api/workforce";
import { formatDateTime } from "../../utils/formatters";

type WorkflowVersionsPanelProps = {
    workflowId: string | null;
    versions: WorkflowVersionSummary[];
    diff: WorkflowDiffResponse | null;
    diffLoading: boolean;
    publishedVersionId?: string | null;
    onPublish: () => void;
    onRollback: (versionId: string) => void;
    publishPending: boolean;
    rollbackPending: boolean;
};

export function WorkflowVersionsPanel({
    workflowId,
    versions,
    diff,
    diffLoading,
    publishedVersionId,
    onPublish,
    onRollback,
    publishPending,
    rollbackPending,
}: WorkflowVersionsPanelProps) {
    if (!workflowId) {
        return <Alert severity="info">Save a draft to manage versions, diff, and rollback.</Alert>;
    }

    return (
        <Stack spacing={2}>
            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                <Button
                    variant="contained"
                    startIcon={<PlayArrow />}
                    onClick={onPublish}
                    disabled={publishPending}
                >
                    Publish draft
                </Button>
            </Stack>

            <Box>
                <Typography variant="subtitle2" gutterBottom>
                    Draft vs published
                </Typography>
                {diffLoading ? (
                    <CircularProgress size={20} />
                ) : diff ? (
                    <Stack spacing={1}>
                        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                            <Chip size="small" label={`+${diff.summary.nodes_added ?? 0} nodes`} />
                            <Chip size="small" label={`-${diff.summary.nodes_removed ?? 0} nodes`} />
                            <Chip size="small" label={`~${diff.summary.nodes_changed ?? 0} changed`} />
                            <Chip
                                size="small"
                                color={diff.graph_changed ? "warning" : "success"}
                                label={diff.graph_changed ? "Graph changed" : "Identical graph"}
                            />
                        </Stack>
                        {diff.nodes_added.length > 0 && (
                            <Typography variant="caption" color="text.secondary">
                                Added: {diff.nodes_added.join(", ")}
                            </Typography>
                        )}
                        {diff.nodes_removed.length > 0 && (
                            <Typography variant="caption" color="text.secondary">
                                Removed: {diff.nodes_removed.join(", ")}
                            </Typography>
                        )}
                        {diff.nodes_changed.length > 0 && (
                            <Typography variant="caption" color="text.secondary">
                                Changed: {diff.nodes_changed.map((item) => `${item.id} (${item.changed_fields.join(", ")})`).join("; ")}
                            </Typography>
                        )}
                    </Stack>
                ) : (
                    <Alert severity="info">No published version yet — first publish will create v1.</Alert>
                )}
            </Box>

            <Divider />

            <Box>
                <Typography variant="subtitle2" gutterBottom>
                    Published versions
                </Typography>
                {!versions.length ? (
                    <Typography variant="body2" color="text.secondary">
                        No published versions.
                    </Typography>
                ) : (
                    <Stack spacing={1}>
                        {versions.map((version) => (
                            <Stack
                                key={version.id}
                                direction={{ xs: "column", sm: "row" }}
                                justifyContent="space-between"
                                alignItems={{ sm: "center" }}
                                sx={{ p: 1.25, border: 1, borderColor: "divider", borderRadius: 1 }}
                                spacing={1}
                            >
                                <Box>
                                    <Typography variant="subtitle2">
                                        v{version.version_number}
                                        {publishedVersionId === version.id ? " · active" : ""}
                                    </Typography>
                                    <Typography variant="caption" color="text.secondary">
                                        {version.created_at ? formatDateTime(String(version.created_at)) : version.id.slice(0, 8)}
                                        {version.graph_hash ? ` · ${version.graph_hash.slice(0, 8)}` : ""}
                                    </Typography>
                                </Box>
                                <Button
                                    size="small"
                                    variant="outlined"
                                    disabled={rollbackPending || publishedVersionId === version.id}
                                    onClick={() => onRollback(version.id)}
                                >
                                    Rollback
                                </Button>
                            </Stack>
                        ))}
                    </Stack>
                )}
            </Box>
        </Stack>
    );
}

type WorkflowTestRunPanelProps = {
    workflowId: string | null;
    selectedNodeId: string | null;
    canRunFromSelected: boolean;
    fixtureJson: string;
    onFixtureChange: (value: string) => void;
    onTestRun: () => void;
    pending: boolean;
};

export function WorkflowTestRunPanel({
    workflowId,
    selectedNodeId,
    canRunFromSelected,
    fixtureJson,
    onFixtureChange,
    onTestRun,
    pending,
}: WorkflowTestRunPanelProps) {
    return (
        <Stack spacing={1.5}>
            <Typography variant="body2" color="text.secondary">
                Test runs execute the saved draft with simulated external writes. Provide fixture input as JSON.
            </Typography>
            <TextField
                label="Test fixture (JSON input)"
                value={fixtureJson}
                onChange={(event) => onFixtureChange(event.target.value)}
                multiline
                minRows={4}
                fullWidth
                size="small"
                placeholder='{"email": {"subject": "Hello"}}'
            />
            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                <Button
                    variant="contained"
                    startIcon={<Science />}
                    onClick={onTestRun}
                    disabled={!workflowId || pending}
                >
                    Test run draft
                </Button>
            </Stack>
            {selectedNodeId && (
                <Alert severity={canRunFromSelected ? "success" : "info"}>
                    {canRunFromSelected
                        ? `Selected node ${selectedNodeId} is the workflow entry — test run starts here.`
                        : `Run-from-node is only enabled when the selected node is the entry trigger. Selected: ${selectedNodeId}.`}
                </Alert>
            )}
            <Alert severity="info">
                Run-until-node is not supported yet — test mode always walks the full draft graph with external writes simulated.
            </Alert>
        </Stack>
    );
}
