/** Extract human-readable API error text from apiFetch failures. */

export function extractApiErrorMessage(error: unknown, fallback: string): string {
    if (error instanceof Error && error.message.trim()) {
        return error.message.trim();
    }
    if (typeof error === "object" && error && "detail" in error) {
        const detail = (error as { detail?: unknown }).detail;
        if (typeof detail === "string" && detail.trim()) return detail;
        if (typeof detail === "object" && detail && "message" in detail) {
            const message = (detail as { message?: unknown }).message;
            if (typeof message === "string" && message.trim()) return message;
        }
    }
    return fallback;
}
