import { useState } from "react";
import { useQueries, useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";

import {
    getAiDocument,
    listAiDatasetCases,
    listAiDatasets,
    listAiDocuments,
    listAiEvaluationRuns,
    listAiReviews,
    listPromptTemplates,
    listPromptVersions,
    type AiOverview,
} from "../../../api/ai";
import { queryKeys } from "../../../config/queryKeys";
import { parseStudioSection, type AiSection } from "../formUtils";

const INDEXING_STATES = new Set(["pending", "queued", "running", "processing"]);

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
    const needsPrompts = ["prompts", "playground", "versions", "datasets"].includes(activeSection);
    const needsDocuments = ["playground", "documents", "retrieval"].includes(activeSection);

    const { data: promptTemplates = [] } = useQuery({
        queryKey: ["ai", "prompts"],
        queryFn: listPromptTemplates,
        enabled: needsPrompts,
    });
    const { data: baseDocuments = [] } = useQuery({
        queryKey: ["ai", "documents"],
        queryFn: listAiDocuments,
        enabled: needsDocuments,
    });
    const statusQueries = useQueries({
        queries: baseDocuments
            .filter((document) => INDEXING_STATES.has(document.ingestion_status))
            .map((document) => ({
                queryKey: ["ai", "documents", document.id],
                queryFn: () => getAiDocument(document.id),
                refetchInterval: (query: { state: { data?: { ingestion_status: string } } }) =>
                    query.state.data && !INDEXING_STATES.has(query.state.data.ingestion_status) ? false : 2500,
            })),
    });
    const statusById = new Map(
        statusQueries.flatMap((query) => query.data ? [[query.data.id, query.data] as const] : []),
    );
    const documents = baseDocuments.map((document) => statusById.get(document.id) ?? document);
    const { data: reviews = [] } = useQuery({
        queryKey: queryKeys.ai.reviews,
        queryFn: listAiReviews,
        enabled: activeSection === "reviews",
    });
    const { data: datasets = [] } = useQuery({
        queryKey: queryKeys.ai.datasets,
        queryFn: listAiDatasets,
        enabled: activeSection === "datasets",
    });
    const { data: evaluationRuns = [] } = useQuery({
        queryKey: queryKeys.ai.evaluationRuns,
        queryFn: listAiEvaluationRuns,
        enabled: activeSection === "datasets",
    });
    const { data: selectedTemplateVersions = [] } = useQuery({
        queryKey: queryKeys.ai.promptVersions(selectedTemplateId),
        queryFn: () => listPromptVersions(selectedTemplateId),
        enabled: selectedTemplateId.length > 0,
    });
    const { data: selectedDatasetCases = [] } = useQuery({
        queryKey: queryKeys.ai.datasetCases(selectedDatasetId),
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
        promptTemplates,
        documents,
        datasets,
        recentRuns: overview.recent_runs,
        providers: overview.providers,
        counts: {
            promptTemplates: overview.prompt_template_count,
            documents: overview.document_count,
            pendingReviews: overview.pending_review_count,
            datasets: overview.dataset_count,
        },
    };
}
