import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";

import { listAiDatasetCases, listAiEvaluationRuns, listAiReviews, listPromptVersions, type AiOverview } from "../../../api/ai";
import { parseStudioSection, type AiSection } from "../formUtils";

export function useAiStudioOverview(overview: AiOverview) {
    const [searchParams, setSearchParams] = useSearchParams();
    const activeSection = parseStudioSection(searchParams.get("studio"));
    const setActiveSection = (value: AiSection) => {
        const next = new URLSearchParams(searchParams);
        next.set("studio", value);
        setSearchParams(next, { replace: true });
    };

    const [selectedTemplateId, setSelectedTemplateId] = useState("");
    const [selectedDatasetId, setSelectedDatasetId] = useState("");
    const [selectedDocumentIds, setSelectedDocumentIds] = useState<string[]>([]);

    const { data: reviews = [] } = useQuery({
        queryKey: ["ai", "reviews"],
        queryFn: listAiReviews,
    });
    const { data: evaluationRuns = [] } = useQuery({
        queryKey: ["ai", "evaluation-runs"],
        queryFn: listAiEvaluationRuns,
    });
    const { data: selectedTemplateVersions = [] } = useQuery({
        queryKey: ["ai", "prompt-versions", selectedTemplateId],
        queryFn: () => listPromptVersions(selectedTemplateId),
        enabled: selectedTemplateId.length > 0,
    });
    const { data: selectedDatasetCases = [] } = useQuery({
        queryKey: ["ai", "dataset-cases", selectedDatasetId],
        queryFn: () => listAiDatasetCases(selectedDatasetId),
        enabled: selectedDatasetId.length > 0,
    });

    function toggleDocument(documentId: string) {
        setSelectedDocumentIds((current) =>
            current.includes(documentId)
                ? current.filter((item) => item !== documentId)
                : [...current, documentId],
        );
    }

    return {
        activeSection,
        setActiveSection,
        selectedTemplateId,
        setSelectedTemplateId,
        selectedDatasetId,
        setSelectedDatasetId,
        selectedDocumentIds,
        toggleDocument,
        reviews,
        evaluationRuns,
        selectedTemplateVersions,
        selectedDatasetCases,
        promptTemplates: overview.prompt_templates,
        documents: overview.documents,
        datasets: overview.datasets,
        recentRuns: overview.recent_runs,
        providers: overview.providers,
    };
}
