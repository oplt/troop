import { Button, Stack } from "@mui/material";
import { ErrorOutline as ErrorOutlineIcon, Hub as ProjectIcon, Refresh as RefreshIcon } from "@mui/icons-material";
import { Link as RouterLink } from "react-router-dom";

import { EmptyState } from "../../../components/ui/EmptyState";
import { PageShell } from "../../../components/ui/PageShell";
import { PageSkeleton } from "../../../components/ui/PageSkeleton";

export function ProjectDetailMissingState() {
    return (
        <PageShell maxWidth="xl">
            <EmptyState
                icon={<ProjectIcon />}
                title="Project not found"
                description="This page needs a project id in the URL."
                action={<Button variant="contained" component={RouterLink} to="/projects">Back to projects</Button>}
            />
        </PageShell>
    );
}

export function ProjectDetailLoadingState() {
    return (
        <PageShell maxWidth="xl">
            <PageSkeleton variant="inspector" />
        </PageShell>
    );
}

export function ProjectDetailErrorState({ message, notFound, retrying, onRetry }: {
    message: string;
    notFound: boolean;
    retrying: boolean;
    onRetry: () => void;
}) {
    return (
        <PageShell maxWidth="xl">
            <EmptyState
                icon={<ErrorOutlineIcon />}
                title={notFound ? "Project not found" : "Couldn't load project"}
                description={message}
                action={
                    <Stack direction={{ xs: "column", sm: "row" }} spacing={1} useFlexGap>
                        <Button variant="contained" startIcon={<RefreshIcon />} disabled={retrying} onClick={onRetry}>
                            {retrying ? "Retrying…" : "Try again"}
                        </Button>
                        <Button variant="outlined" component={RouterLink} to="/projects">Back to projects</Button>
                    </Stack>
                }
            />
        </PageShell>
    );
}
