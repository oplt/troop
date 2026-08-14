import { Alert, Button, Dialog, DialogActions, DialogContent, DialogTitle, Stack, TextField } from "@mui/material";

import type { EmailApprovalView } from "../../approvals/emailApproval";

type EmailDraft = EmailApprovalView["draft"];

type EmailApprovalEditorProps = {
    open: boolean;
    draft: EmailDraft;
    isSaving: boolean;
    onDraftChange: (updater: (current: EmailDraft) => EmailDraft) => void;
    onClose: () => void;
    onSave: () => void;
};

export function EmailApprovalEditor({
    open,
    draft,
    isSaving,
    onDraftChange,
    onClose,
    onSave,
}: EmailApprovalEditorProps) {
    return (
        <Dialog open={open} onClose={() => !isSaving && onClose()} fullWidth maxWidth="md">
            <DialogTitle>Edit proposed email</DialogTitle>
            <DialogContent>
                <Stack spacing={2} sx={{ pt: 1 }}>
                    <Alert severity="warning">
                        Editing invalidates the previous content hash. The updated draft must be approved again before
                        sending.
                    </Alert>
                    <TextField
                        label="To"
                        value={draft.to.join(", ")}
                        onChange={(event) =>
                            onDraftChange((current) => ({
                                ...current,
                                to: event.target.value
                                    .split(",")
                                    .map((item) => item.trim())
                                    .filter(Boolean),
                            }))
                        }
                        fullWidth
                    />
                    <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
                        <TextField
                            label="CC"
                            value={draft.cc.join(", ")}
                            onChange={(event) =>
                                onDraftChange((current) => ({
                                    ...current,
                                    cc: event.target.value
                                        .split(",")
                                        .map((item) => item.trim())
                                        .filter(Boolean),
                                }))
                            }
                            fullWidth
                        />
                        <TextField
                            label="BCC"
                            value={draft.bcc.join(", ")}
                            onChange={(event) =>
                                onDraftChange((current) => ({
                                    ...current,
                                    bcc: event.target.value
                                        .split(",")
                                        .map((item) => item.trim())
                                        .filter(Boolean),
                                }))
                            }
                            fullWidth
                        />
                    </Stack>
                    <TextField
                        label="Subject"
                        value={draft.subject}
                        onChange={(event) =>
                            onDraftChange((current) => ({ ...current, subject: event.target.value }))
                        }
                        fullWidth
                    />
                    <TextField
                        label="Reply"
                        value={draft.body_text}
                        onChange={(event) =>
                            onDraftChange((current) => ({ ...current, body_text: event.target.value }))
                        }
                        multiline
                        minRows={8}
                        fullWidth
                    />
                </Stack>
            </DialogContent>
            <DialogActions>
                <Button onClick={onClose} disabled={isSaving}>
                    Cancel
                </Button>
                <Button
                    variant="contained"
                    onClick={onSave}
                    disabled={isSaving || !draft.to.length || !draft.body_text.trim()}
                >
                    Save revised draft
                </Button>
            </DialogActions>
        </Dialog>
    );
}
