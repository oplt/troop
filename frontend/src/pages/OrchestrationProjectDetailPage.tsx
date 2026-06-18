import { lazy, Suspense } from "react";
import { CircularProgress, Stack, Typography } from "@mui/material";

import { PageShell } from "../components/ui/PageShell";

const OrchestrationProjectDetailView = lazy(
    () => import("./projectDetail/OrchestrationProjectDetailView"),
);

export default function OrchestrationProjectDetailPage() {
    return (
        <Suspense
            fallback={
                <PageShell maxWidth="xl">
                    <Stack
                        spacing={2}
                        alignItems="center"
                        sx={{ py: 8 }}
                        role="status"
                        aria-live="polite"
                        aria-busy="true"
                    >
                        <CircularProgress size={32} aria-hidden />
                        <Typography color="text.secondary">Loading project workspace...</Typography>
                    </Stack>
                </PageShell>
            }
        >
            <OrchestrationProjectDetailView />
        </Suspense>
    );
}
