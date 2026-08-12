import { Alert, Button, CircularProgress, Stack, Typography } from "@mui/material";
import { extractApiErrorMessage } from "../../utils/apiErrors";

type QueryStateProps = {
    loading: boolean;
    error?: unknown;
    empty?: boolean;
    emptyMessage?: string;
    onRetry?: () => void;
    children: React.ReactNode;
};

export function QueryState({ loading, error, empty, emptyMessage = "No results yet.", onRetry, children }: QueryStateProps) {
    if (loading) {
        return (
            <Stack alignItems="center" spacing={1.5} sx={{ py: 5 }} role="status" aria-live="polite">
                <CircularProgress size={24} aria-label="Loading" />
                <Typography color="text.secondary">Loading…</Typography>
            </Stack>
        );
    }

    if (error) {
        return (
            <Alert
                severity="error"
                action={onRetry ? <Button color="inherit" size="small" onClick={onRetry}>Retry</Button> : undefined}
            >
                {extractApiErrorMessage(error, "We couldn't load this section.")}
            </Alert>
        );
    }

    if (empty) {
        return <Typography color="text.secondary">{emptyMessage}</Typography>;
    }

    return <>{children}</>;
}
