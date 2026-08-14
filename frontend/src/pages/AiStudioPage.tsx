import { useQuery } from "@tanstack/react-query";
import { Box, Button, Skeleton } from "@mui/material";
import { ErrorOutline as ErrorOutlineIcon, Refresh as RefreshIcon } from "@mui/icons-material";

import { getAiOverview } from "../api/ai";
import { EmptyState } from "../components/ui/EmptyState";
import { PageShell } from "../components/ui/PageShell";
import { extractApiErrorMessage } from "../utils/apiErrors";
import { AiStudioContent } from "../features/aiStudio/AiStudioContent";

export default function AiStudioPage() {
    const { data: overview, isLoading, isError, error, refetch, isFetching } = useQuery({
        queryKey: ["ai", "overview"],
        queryFn: getAiOverview,
        refetchInterval: (query) => {
            const docs = query.state.data?.documents ?? [];
            return docs.some((doc) => doc.ingestion_status === "pending" || doc.ingestion_status === "running")
                ? 2500
                : false;
        },
    });

    if (isLoading) {
        return (
            <Box sx={{ display: "grid", placeItems: "center", minHeight: "100vh" }}>
                <Skeleton variant="rounded" width="92%" height={520} sx={{ borderRadius: 6 }} />
            </Box>
        );
    }

    if (isError) {
        const message = extractApiErrorMessage(error, "Couldn't load AI Studio. Check your connection and try again.");
        return (
            <PageShell maxWidth="xl">
                <EmptyState
                    icon={<ErrorOutlineIcon />}
                    title="Couldn't load AI Studio"
                    description={message}
                    action={
                        <Button
                            variant="contained"
                            startIcon={<RefreshIcon />}
                            disabled={isFetching}
                            onClick={() => {
                                void refetch();
                            }}
                        >
                            {isFetching ? "Retrying…" : "Try again"}
                        </Button>
                    }
                />
            </PageShell>
        );
    }

    if (!overview) {
        return null;
    }

    return <AiStudioContent overview={overview} />;
}
