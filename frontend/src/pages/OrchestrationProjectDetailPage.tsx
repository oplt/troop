import { lazy, Suspense } from "react";

import { PageShell } from "../components/ui/PageShell";
import { PageSkeleton } from "../components/ui/PageSkeleton";

const OrchestrationProjectDetailView = lazy(
    () => import("./projectDetail/OrchestrationProjectDetailView"),
);

export default function OrchestrationProjectDetailPage() {
    return (
        <Suspense
            fallback={
                <PageShell maxWidth="xl">
                    <PageSkeleton variant="inspector" />
                </PageShell>
            }
        >
            <OrchestrationProjectDetailView />
        </Suspense>
    );
}
