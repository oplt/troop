import {
    Approval as ReviewIcon,
    Dataset as DatasetIcon,
    Description as DocumentIcon,
    PsychologyAlt as PromptIcon,
} from "@mui/icons-material";

import { AnalyticsKpiStrip } from "../../components/ui/AnalyticsKpiStrip";
import { StatCard } from "../../components/ui/StatCard";

type AiStudioOverviewProps = {
    promptTemplateCount: number;
    documentCount: number;
    pendingReviewCount: number;
    datasetCount: number;
};

export function AiStudioOverview({
    promptTemplateCount,
    documentCount,
    pendingReviewCount,
    datasetCount,
}: AiStudioOverviewProps) {
    return (
        <AnalyticsKpiStrip columns={{ xs: 1, sm: 2, md: 4, lg: 4 }}>
            <StatCard
                label="Prompt templates"
                value={promptTemplateCount}
                description="Reusable prompts with version history"
                icon={<PromptIcon />}
            />
            <StatCard
                label="Documents"
                value={documentCount}
                description="Indexed retrieval sources"
                icon={<DocumentIcon />}
                color="secondary"
            />
            <StatCard
                label="Pending reviews"
                value={pendingReviewCount}
                description="Runs waiting for human review"
                icon={<ReviewIcon />}
                color="warning"
            />
            <StatCard
                label="Datasets"
                value={datasetCount}
                description="Saved evaluation datasets"
                icon={<DatasetIcon />}
                color="success"
            />
        </AnalyticsKpiStrip>
    );
}
