import { useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import {
    Alert,
    Box,
    Button,
    Chip,
    CircularProgress,
    Paper,
    Stack,
    TextField,
    Typography,
} from "@mui/material";
import {
    Check as ApproveIcon,
    Close as RejectIcon,
    TaskAlt as TaskIcon,
    PlayArrow as RunIcon,
    Info as InfoIcon,
    EditOutlined as EditIcon,
    RateReviewOutlined as RequestChangesIcon,
} from "@mui/icons-material";

import type { Approval } from "../../../api/orchestration";
import { decideApproval } from "../../../api/orchestration";
import { editEmailApprovalPayload, requestApprovalChanges } from "../../../api/integrations";
import { useSnackbar } from "../../../app/snackbarContext";
import { StatusChip } from "../../../components/ui/StatusChip";
import { queryKeys } from "../../../config/queryKeys";
import { formatDateTime } from "../../../utils/formatters";
import { normalizeEmailApproval } from "../../approvals/emailApproval";
import { describeAction, emailConsequenceLine } from "../approvalUtils";
import { EmailApprovalDetails } from "../email/EmailApprovalDetails";
import { EmailApprovalEditor } from "../email/EmailApprovalEditor";

type ApprovalCardProps = {
    approval: Approval;
    focused?: boolean;
    onFocusCard?: () => void;
};

export function ApprovalCard({ approval, focused = false, onFocusCard }: ApprovalCardProps) {
    const [reason, setReason] = useState("");
    const [editOpen, setEditOpen] = useState(false);
    const email = normalizeEmailApproval(approval.payload, approval.approval_type);
    const [emailDraft, setEmailDraft] = useState(email.draft);
    const queryClient = useQueryClient();
    const { showToast } = useSnackbar();
    const navigate = useNavigate();
    const cardRef = useRef<HTMLDivElement | null>(null);

    useEffect(() => {
        if (!focused || !cardRef.current) return;
        cardRef.current.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }, [focused]);

    const mutation = useMutation({
        mutationFn: ({ status, reason: r }: { status: "approved" | "rejected"; reason?: string }) =>
            decideApproval(approval.id, { status, reason: r }),
        onSuccess: async (decision) => {
            await queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.approvals });
            await queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.approvalsPendingCount });
            await queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.runsRoot });
            showToast({
                message:
                    decision.run_id && decision.status === "approved"
                        ? "Approval saved; the blocked run is being queued to resume."
                        : "Approval decision saved.",
                severity: "success",
            });
        },
        onError: (error) => {
            showToast({
                message: error instanceof Error ? error.message : "Couldn't save the approval decision.",
                severity: "error",
            });
        },
    });
    const editMutation = useMutation({
        mutationFn: () => editEmailApprovalPayload(approval.id, emailDraft),
        onSuccess: async () => {
            setEditOpen(false);
            await queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.approvals });
            showToast({ message: "Draft updated. Review and approve the new exact version.", severity: "success" });
        },
        onError: (error) =>
            showToast({ message: error instanceof Error ? error.message : "Draft update failed.", severity: "error" }),
    });
    const requestChangesMutation = useMutation({
        mutationFn: () => requestApprovalChanges(approval.id, reason),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.approvals });
            showToast({ message: "Changes requested on the canonical approval.", severity: "success" });
        },
        onError: (error) =>
            showToast({ message: error instanceof Error ? error.message : "Request failed.", severity: "error" }),
    });

    const isPending = approval.status === "pending";
    const actionDescription = describeAction(approval);
    const consequence = emailConsequenceLine(approval);

    return (
        <Paper
            ref={cardRef}
            onClick={onFocusCard}
            tabIndex={isPending ? 0 : -1}
            onFocus={onFocusCard}
            sx={{
                p: 2,
                borderRadius: 1,
                outline: focused ? (t) => `2px solid ${t.palette.primary.main}` : "none",
                outlineOffset: 2,
                border: (t) => (isPending ? `1px solid ${t.palette.warning.light}` : "1px solid transparent"),
                bgcolor: (t) => (!isPending ? t.palette.action.hover : "transparent"),
            }}
        >
            <Stack spacing={1.5}>
                <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                    <Typography variant="subtitle2" sx={{ fontWeight: 500 }}>
                        {actionDescription}
                    </Typography>
                    <StatusChip
                        status={approval.status}
                        kind="approval"
                        variant={isPending ? "outlined" : "filled"}
                        celebrate={approval.status === "approved"}
                    />
                    {approval.approval_type.includes("escalation") && (
                        <Chip label="Escalation" size="small" variant="outlined" color="info" />
                    )}
                </Stack>

                <Stack direction="row" spacing={1.5} alignItems="center" flexWrap="wrap" useFlexGap>
                    {approval.task_id && (
                        <Stack direction="row" spacing={0.5} alignItems="center">
                            <TaskIcon fontSize="small" sx={{ color: "text.secondary" }} />
                            {approval.project_id ? (
                                <Button
                                    size="small"
                                    variant="text"
                                    sx={{ p: 0, minWidth: "auto", fontSize: "0.75rem" }}
                                    onClick={() => navigate(`/projects/${approval.project_id}`)}
                                >
                                    Task {approval.task_id.slice(0, 8)}
                                </Button>
                            ) : (
                                <Typography variant="caption" color="text.secondary">
                                    Task: {approval.task_id.slice(0, 8)}
                                </Typography>
                            )}
                        </Stack>
                    )}
                    {approval.run_id && (
                        <Stack direction="row" spacing={0.5} alignItems="center">
                            <RunIcon fontSize="small" sx={{ color: "text.secondary" }} />
                            <Button
                                size="small"
                                variant="text"
                                sx={{ p: 0, minWidth: "auto", fontSize: "0.75rem" }}
                                onClick={() => navigate(`/runs/${approval.run_id}`)}
                            >
                                Run {approval.run_id.slice(0, 8)}
                            </Button>
                        </Stack>
                    )}
                    {approval.issue_link_id && (
                        <Typography variant="caption" color="text.secondary">
                            Issue link: {approval.issue_link_id.slice(0, 8)}
                        </Typography>
                    )}
                    <Typography variant="caption" color="text.secondary" sx={{ ml: "auto" }}>
                        {formatDateTime(approval.created_at)}
                    </Typography>
                </Stack>

                {email.isEmail ? (
                    <EmailApprovalDetails approval={approval} />
                ) : (
                    Object.keys(approval.payload).length > 0 && (
                        <Box
                            sx={{
                                p: 1.25,
                                borderRadius: 1,
                                bgcolor: "background.default",
                                border: 1,
                                borderColor: "divider",
                                fontFamily: "monospace",
                                fontSize: "0.78rem",
                                maxHeight: 120,
                                overflow: "auto",
                                whiteSpace: "pre-wrap",
                            }}
                        >
                            {JSON.stringify(approval.payload, null, 2)}
                        </Box>
                    )
                )}

                {!isPending && approval.reason && (
                    <Alert
                        severity={approval.status === "approved" ? "success" : "warning"}
                        sx={{ py: 0.5, px: 1.5 }}
                        icon={<InfoIcon fontSize="small" />}
                    >
                        <Typography variant="caption">{approval.reason}</Typography>
                    </Alert>
                )}

                {isPending && (
                    <>
                        {consequence ? (
                            <Alert severity="warning" sx={{ py: 0.75 }}>
                                <Typography variant="body2">{consequence}</Typography>
                            </Alert>
                        ) : null}
                        <TextField
                            size="small"
                            label="Decision note"
                            value={reason}
                            onChange={(e) => setReason(e.target.value)}
                            disabled={mutation.isPending}
                            helperText="A rejection requires a reason."
                        />
                        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                            <Button
                                size="small"
                                variant="contained"
                                startIcon={mutation.isPending ? <CircularProgress size={16} /> : <ApproveIcon />}
                                onClick={() => mutation.mutate({ status: "approved", reason: reason || undefined })}
                                disabled={mutation.isPending || email.stale}
                            >
                                {email.isEmail ? "Approve & Send" : "Approve"}
                            </Button>
                            {email.isEmail && (
                                <Button
                                    size="small"
                                    variant="outlined"
                                    startIcon={<EditIcon />}
                                    disabled={mutation.isPending}
                                    onClick={() => setEditOpen(true)}
                                >
                                    Edit
                                </Button>
                            )}
                            <Button
                                size="small"
                                variant="outlined"
                                color="error"
                                startIcon={mutation.isPending ? <CircularProgress size={16} /> : <RejectIcon />}
                                disabled={mutation.isPending || !reason.trim()}
                                onClick={() => mutation.mutate({ status: "rejected", reason: reason || undefined })}
                            >
                                Reject
                            </Button>
                            {email.isEmail && (
                                <Button
                                    size="small"
                                    variant="outlined"
                                    startIcon={<RequestChangesIcon />}
                                    disabled={requestChangesMutation.isPending || !reason.trim()}
                                    onClick={() => requestChangesMutation.mutate()}
                                >
                                    Request changes
                                </Button>
                            )}
                        </Stack>
                    </>
                )}
            </Stack>
            <EmailApprovalEditor
                open={editOpen}
                draft={emailDraft}
                isSaving={editMutation.isPending}
                onDraftChange={setEmailDraft}
                onClose={() => setEditOpen(false)}
                onSave={() => editMutation.mutate()}
            />
        </Paper>
    );
}
