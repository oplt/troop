import { useQuery } from "@tanstack/react-query";
import {
    Alert,
    Box,
    Button,
    Chip,
    CircularProgress,
    Dialog,
    DialogActions,
    DialogContent,
    DialogTitle,
    Paper,
    Stack,
    Typography,
} from "@mui/material";
import { CheckCircle as PassIcon, Cancel as FailIcon } from "@mui/icons-material";
import { checkTaskAcceptance } from "../../../../api/orchestration";
import { queryKeys } from "../../../../config/queryKeys";
import { extractApiErrorMessage } from "../../../../utils/apiErrors";

type AcceptanceCriterionItem = {
    item: string;
    passed: boolean;
    evidence_excerpt?: string;
};

function getAcceptanceItems(check: { name: string } & Record<string, unknown>): AcceptanceCriterionItem[] {
    if (check.name !== "acceptance_criteria" || !Array.isArray(check.items)) {
        return [];
    }
    return check.items.filter((item): item is AcceptanceCriterionItem => {
        if (typeof item !== "object" || item === null) return false;
        const candidate = item as Partial<AcceptanceCriterionItem>;
        return typeof candidate.item === "string" && typeof candidate.passed === "boolean";
    });
}

export function AcceptanceDialog({
    projectId,
    taskId,
    taskTitle,
    onClose,
}: {
    projectId: string;
    taskId: string;
    taskTitle: string;
    onClose: () => void;
}) {
    const { data, isLoading, error, refetch, isFetching } = useQuery({
        queryKey: queryKeys.orchestration.acceptance(taskId),
        queryFn: () => checkTaskAcceptance(projectId, taskId),
    });

    return (
        <Dialog open onClose={onClose} maxWidth="sm" fullWidth>
            <DialogTitle>Acceptance check — {taskTitle}</DialogTitle>
            <DialogContent>
                {isLoading && <CircularProgress size={24} />}
                {error && (
                    <Alert
                        severity="error"
                        sx={{ mt: isLoading ? 1 : 0 }}
                        action={
                            <Button color="inherit" size="small" disabled={isFetching} onClick={() => void refetch()}>
                                {isFetching ? "Retrying…" : "Retry"}
                            </Button>
                        }
                    >
                        {extractApiErrorMessage(error, "Acceptance check failed.")}
                    </Alert>
                )}
                {data && (
                    <Stack spacing={1.5} sx={{ mt: 1 }}>
                        <Chip label={data.passed ? "All checks passed" : "Some checks failed"} color={data.passed ? "success" : "error"} />
                        <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
                            {Array.isArray(data.config.required_artifact_kinds) && data.config.required_artifact_kinds.length > 0 ? (
                                <Chip size="small" variant="outlined" label={`Artifacts: ${(data.config.required_artifact_kinds as unknown[]).map(String).join(", ")}`} />
                            ) : null}
                            {data.config.require_github_comment ? <Chip size="small" variant="outlined" label="Needs GitHub comment" /> : null}
                            {data.config.require_github_pr ? <Chip size="small" variant="outlined" label="Needs GitHub PR" /> : null}
                            {data.config.require_reviewer_approval ? <Chip size="small" variant="outlined" label="Needs reviewer approval" /> : null}
                        </Stack>
                        {data.checks.map((check) => {
                            const acceptanceItems = getAcceptanceItems(check as { name: string } & Record<string, unknown>);
                            return (
                                <Stack key={check.name} spacing={0.75}>
                                    <Stack direction="row" spacing={1} alignItems="flex-start">
                                        {check.passed ? <PassIcon color="success" fontSize="small" /> : <FailIcon color="error" fontSize="small" />}
                                        <Box>
                                            <Typography variant="body2">{check.name}</Typography>
                                            <Typography variant="caption" color="text.secondary">{check.detail}</Typography>
                                        </Box>
                                    </Stack>
                                    {acceptanceItems.length > 0 ? (
                                        <Stack spacing={0.75} sx={{ ml: 3 }}>
                                            {acceptanceItems.map((item) => (
                                                <Paper key={item.item} variant="outlined" sx={{ p: 1, borderRadius: 1 }}>
                                                    <Stack direction="row" spacing={1} alignItems="flex-start">
                                                        {item.passed ? <PassIcon color="success" fontSize="small" /> : <FailIcon color="error" fontSize="small" />}
                                                        <Box>
                                                            <Typography variant="body2">{item.item}</Typography>
                                                            {item.evidence_excerpt ? <Typography variant="caption" color="text.secondary">Evidence: {item.evidence_excerpt}</Typography> : null}
                                                        </Box>
                                                    </Stack>
                                                </Paper>
                                            ))}
                                        </Stack>
                                    ) : null}
                                </Stack>
                            );
                        })}
                    </Stack>
                )}
            </DialogContent>
            <DialogActions><Button onClick={onClose}>Close</Button></DialogActions>
        </Dialog>
    );
}
