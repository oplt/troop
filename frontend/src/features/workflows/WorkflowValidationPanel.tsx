import {
    Alert,
    Box,
    Button,
    Chip,
    List,
    ListItemButton,
    ListItemText,
    Stack,
    Typography,
} from "@mui/material";
import type { WorkflowValidationIssue } from "./validationIssues";

type WorkflowValidationPanelProps = {
    issues: WorkflowValidationIssue[];
    serverValid: boolean | null;
    onFocusNode: (nodeId: string) => void;
};

export function WorkflowValidationPanel({
    issues,
    serverValid,
    onFocusNode,
}: WorkflowValidationPanelProps) {
    const errors = issues.filter((issue) => issue.severity === "error");
    const warnings = issues.filter((issue) => issue.severity === "warning");
    const infos = issues.filter((issue) => issue.severity === "info");

    if (!issues.length && serverValid === null) {
        return (
            <Alert severity="info">
                Save a draft to fetch server validation, or edit the graph to see client checks.
            </Alert>
        );
    }

    return (
        <Stack spacing={1.25}>
            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                <Chip
                    label={`${errors.length} error${errors.length === 1 ? "" : "s"}`}
                    size="small"
                    color={errors.length ? "error" : "default"}
                    variant="outlined"
                />
                <Chip
                    label={`${warnings.length} warning${warnings.length === 1 ? "" : "s"}`}
                    size="small"
                    color={warnings.length ? "warning" : "default"}
                    variant="outlined"
                />
                {serverValid !== null && (
                    <Chip
                        label={serverValid ? "Server: valid" : "Server: blocked"}
                        size="small"
                        color={serverValid ? "success" : "error"}
                        variant="outlined"
                    />
                )}
            </Stack>
            {[...errors, ...warnings, ...infos].map((issue) => (
                <Alert
                    key={`${issue.source}-${issue.severity}-${issue.nodeId ?? ""}-${issue.message}`}
                    severity={issue.severity === "info" ? "info" : issue.severity}
                    action={
                        issue.nodeId ? (
                            <Button color="inherit" size="small" onClick={() => onFocusNode(issue.nodeId!)}>
                                Focus
                            </Button>
                        ) : undefined
                    }
                >
                    {issue.message}
                </Alert>
            ))}
            {issues.some((issue) => issue.nodeId) && (
                <Box>
                    <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
                        Nodes with issues
                    </Typography>
                    <List dense disablePadding>
                        {[...new Set(issues.map((issue) => issue.nodeId).filter(Boolean))].map((nodeId) => (
                            <ListItemButton key={nodeId} onClick={() => onFocusNode(nodeId!)} sx={{ borderRadius: 1 }}>
                                <ListItemText primary={nodeId} secondary="Jump to node on canvas" />
                            </ListItemButton>
                        ))}
                    </List>
                </Box>
            )}
        </Stack>
    );
}
