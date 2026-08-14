import {
    Button,
    Dialog,
    DialogActions,
    DialogContent,
    DialogContentText,
    DialogTitle,
} from "@mui/material";

type ConfirmDestructiveDialogProps = {
    open: boolean;
    title: string;
    description: string;
    confirmLabel?: string;
    cancelLabel?: string;
    /** Use "primary" for leave-guards / affirmative confirms; default is destructive. */
    confirmColor?: "error" | "primary";
    loading?: boolean;
    onConfirm: () => void;
    onClose: () => void;
};

/**
 * Shared confirm pattern (delete / disconnect / leave without saving).
 * Prefer this over window.confirm.
 */
export function ConfirmDestructiveDialog({
    open,
    title,
    description,
    confirmLabel = "Delete",
    cancelLabel = "Cancel",
    confirmColor = "error",
    loading = false,
    onConfirm,
    onClose,
}: ConfirmDestructiveDialogProps) {
    return (
        <Dialog open={open} onClose={loading ? undefined : onClose} maxWidth="xs" fullWidth>
            <DialogTitle>{title}</DialogTitle>
            <DialogContent>
                <DialogContentText>{description}</DialogContentText>
            </DialogContent>
            <DialogActions>
                <Button onClick={onClose} disabled={loading}>
                    {cancelLabel}
                </Button>
                <Button color={confirmColor} variant="contained" disabled={loading} onClick={onConfirm} autoFocus>
                    {loading ? "Working…" : confirmLabel}
                </Button>
            </DialogActions>
        </Dialog>
    );
}
