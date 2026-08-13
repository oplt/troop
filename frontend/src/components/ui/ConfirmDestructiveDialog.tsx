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
    loading?: boolean;
    onConfirm: () => void;
    onClose: () => void;
};

/**
 * Shared destructive confirm pattern (delete / disconnect / permanent actions).
 * Prefer this over window.confirm.
 */
export function ConfirmDestructiveDialog({
    open,
    title,
    description,
    confirmLabel = "Delete",
    cancelLabel = "Cancel",
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
                <Button color="error" variant="contained" disabled={loading} onClick={onConfirm} autoFocus>
                    {loading ? "Working…" : confirmLabel}
                </Button>
            </DialogActions>
        </Dialog>
    );
}
