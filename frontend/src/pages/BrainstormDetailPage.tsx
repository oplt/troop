import { useQuery } from "@tanstack/react-query";
import { Typography } from "@mui/material";
import { useParams } from "react-router-dom";

import { getBrainstorm } from "../api/orchestration";
import { PageShell } from "../components/ui/PageShell";
import { BrainstormDetailContent } from "../features/brainstorms/detail/BrainstormDetailContent";

export default function BrainstormDetailPage() {
    const { brainstormId = "" } = useParams();

    const { data: brainstorm, isLoading } = useQuery({
        queryKey: ["orchestration", "brainstorm", brainstormId],
        queryFn: () => getBrainstorm(brainstormId),
        enabled: Boolean(brainstormId),
    });

    if (isLoading || !brainstorm) {
        return (
            <PageShell maxWidth="xl">
                <Typography color="text.secondary">Loading brainstorm room...</Typography>
            </PageShell>
        );
    }

    return <BrainstormDetailContent brainstormId={brainstormId} brainstorm={brainstorm} />;
}
