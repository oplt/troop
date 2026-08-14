import { Alert, Box, Chip, Divider, Paper, Stack, Typography } from "@mui/material";

import type { Approval } from "../../../api/orchestration";
import { humanizeKey } from "../../../utils/formatters";
import { normalizeEmailApproval } from "../../approvals/emailApproval";

type EmailApprovalDetailsProps = {
    approval: Approval;
};

export function EmailApprovalDetails({ approval }: EmailApprovalDetailsProps) {
    const email = normalizeEmailApproval(approval.payload, approval.approval_type);
    const formatAddress = (item: { name?: string; email: string } | null) =>
        item ? (item.name ? `${item.name} <${item.email}>` : item.email) : "Not provided";

    return (
        <Stack spacing={2}>
            {email.stale && (
                <Alert severity="error">
                    This draft is stale or invalidated and must not be sent without a new approval.
                </Alert>
            )}
            <Box
                sx={{
                    display: "grid",
                    gridTemplateColumns: { xs: "1fr", lg: "repeat(2, minmax(0, 1fr))" },
                    gap: 2,
                }}
            >
                <Paper variant="outlined" sx={{ p: 2, borderRadius: 1 }}>
                    <Typography variant="subtitle2">Incoming email</Typography>
                    <Divider sx={{ my: 1 }} />
                    <Typography variant="caption" color="text.secondary">
                        From
                    </Typography>
                    <Typography variant="body2">{formatAddress(email.incoming.from)}</Typography>
                    <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1 }}>
                        Subject
                    </Typography>
                    <Typography variant="body2">{email.incoming.subject || "No subject"}</Typography>
                    <Typography
                        variant="body2"
                        sx={{ mt: 1, whiteSpace: "pre-wrap", maxHeight: 220, overflow: "auto" }}
                    >
                        {email.incoming.body || "Body not included in approval payload."}
                    </Typography>
                </Paper>
                <Paper variant="outlined" sx={{ p: 2, borderRadius: 1 }}>
                    <Typography variant="subtitle2">Proposed reply</Typography>
                    <Divider sx={{ my: 1 }} />
                    <Typography variant="caption" color="text.secondary">
                        To
                    </Typography>
                    <Typography variant="body2">{email.draft.to.join(", ") || "Not provided"}</Typography>
                    <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.5 }}>
                        CC / BCC
                    </Typography>
                    <Typography variant="body2">
                        {email.draft.cc.join(", ") || "—"} / {email.draft.bcc.join(", ") || "—"}
                    </Typography>
                    <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1 }}>
                        Subject
                    </Typography>
                    <Typography variant="body2">{email.draft.subject || "No subject"}</Typography>
                    <Typography
                        variant="body2"
                        sx={{ mt: 1, whiteSpace: "pre-wrap", maxHeight: 220, overflow: "auto" }}
                    >
                        {email.draft.body_text || "Draft body not included."}
                    </Typography>
                </Paper>
            </Box>
            <Stack direction="row" gap={1} flexWrap="wrap" useFlexGap>
                <Chip
                    label={`Risk: ${humanizeKey(email.risk)}`}
                    color={email.risk === "high" ? "error" : email.risk === "medium" ? "warning" : "default"}
                    size="small"
                />
                {email.agent && <Chip label={`Agent: ${email.agent}`} size="small" variant="outlined" />}
                {email.workflow && <Chip label={`Workflow: ${email.workflow}`} size="small" variant="outlined" />}
                {(email.project || email.task) && (
                    <Chip
                        label={[email.project, email.task].filter(Boolean).join(" · ")}
                        size="small"
                        variant="outlined"
                    />
                )}
            </Stack>
            {email.warnings.length > 0 && <Alert severity="warning">{email.warnings.join(" · ")}</Alert>}
            {email.context.length > 0 && (
                <Box>
                    <Typography variant="subtitle2">Context and sources</Typography>
                    <Stack component="ul" sx={{ my: 0.5, pl: 2.5 }}>
                        {email.context.map((item, index) => (
                            <Typography component="li" variant="body2" key={`${item.title}-${index}`}>
                                {item.title}
                                {item.source ? ` · ${item.source}` : ""}
                            </Typography>
                        ))}
                    </Stack>
                </Box>
            )}
        </Stack>
    );
}
