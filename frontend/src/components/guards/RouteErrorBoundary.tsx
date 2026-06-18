import React from "react";
import { Button, Stack, Typography } from "@mui/material";
import { ErrorOutline as ErrorOutlineIcon } from "@mui/icons-material";
import { EmptyState } from "../ui/EmptyState";
import { PageShell } from "../ui/PageShell";

type Props = {
    children: React.ReactNode;
    title?: string;
};

type State = {
    error: Error | null;
};

type SentryScope = {
    setTag?: (key: string, value: string) => void;
    setContext?: (key: string, value: Record<string, unknown>) => void;
};

type SentryClient = {
    captureException?: (error: unknown, context?: Record<string, unknown>) => void;
    withScope?: (callback: (scope: SentryScope) => void) => void;
};

function getRouteErrorTags() {
    const route = typeof window === "undefined" ? "unknown" : window.location.pathname;
    const projectIdMatch = route.match(/\/projects\/([^/]+)/);
    return {
        route,
        project_id: projectIdMatch?.[1] ?? "none",
        source: "route_error_boundary",
    };
}

function reportRouteError(error: Error, info: React.ErrorInfo) {
    const sentry = (globalThis as { Sentry?: SentryClient }).Sentry;
    const tags = getRouteErrorTags();
    if (!sentry?.captureException) {
        return;
    }
    if (sentry.withScope) {
        sentry.withScope((scope) => {
            Object.entries(tags).forEach(([key, value]) => scope.setTag?.(key, value));
            scope.setContext?.("react", { componentStack: info.componentStack });
            sentry.captureException?.(error);
        });
        return;
    }
    sentry.captureException(error, {
        tags,
        extra: { componentStack: info.componentStack },
    });
}

export class RouteErrorBoundary extends React.Component<Props, State> {
    state: State = { error: null };

    static getDerivedStateFromError(error: Error): State {
        return { error };
    }

    componentDidCatch(error: Error, info: React.ErrorInfo) {
        console.error("route_error_boundary", error, info.componentStack);
        reportRouteError(error, info);
    }

    private handleRetry = () => {
        this.setState({ error: null });
    };

    render() {
        if (this.state.error) {
            const message = this.state.error.message || "Something went wrong rendering this page.";
            return (
                <PageShell maxWidth="md">
                    <EmptyState
                        icon={<ErrorOutlineIcon />}
                        title={this.props.title ?? "Page failed to load"}
                        description={message}
                        action={
                            <Stack direction={{ xs: "column", sm: "row" }} spacing={1} useFlexGap>
                                <Button variant="contained" onClick={this.handleRetry}>
                                    Try again
                                </Button>
                                <Button variant="outlined" href="/dashboard">
                                    Back to dashboard
                                </Button>
                            </Stack>
                        }
                    />
                    <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 2 }}>
                        If this keeps happening, refresh the browser or contact support with the time of the error.
                    </Typography>
                </PageShell>
            );
        }
        return this.props.children;
    }
}
