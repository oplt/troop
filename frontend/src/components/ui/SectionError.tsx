import { Alert, Button } from "@mui/material";
import { extractApiErrorMessage } from "../../utils/apiErrors";

type SectionErrorProps = {
    error: unknown;
    fallback?: string;
    onRetry?: () => void;
    retrying?: boolean;
};

/** Inline section failure with optional retry — prefer over stacked bare Alerts. */
export function SectionError({
    error,
    fallback = "Couldn't load this section. Check your connection and try again.",
    onRetry,
    retrying = false,
}: SectionErrorProps) {
    return (
        <Alert
            severity="error"
            action={
                onRetry ? (
                    <Button color="inherit" size="small" disabled={retrying} onClick={onRetry}>
                        {retrying ? "Retrying…" : "Retry"}
                    </Button>
                ) : undefined
            }
        >
            {extractApiErrorMessage(error, fallback)}
        </Alert>
    );
}
