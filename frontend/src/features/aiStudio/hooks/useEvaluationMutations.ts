import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import {
    createAiDataset,
    createAiDatasetCase,
    createAiFeedback,
    createAiReview,
    createAiRun,
    decideAiReview,
    runAiEvaluation,
} from "../../../api/ai";
import { useSnackbar } from "../../../app/snackbarContext";
import type { DatasetCaseFormState, DatasetFormState, RunFormState } from "../types";

type UseEvaluationMutationsOptions = {
    selectedDatasetId: string;
    onDatasetCreated?: (datasetId: string) => void;
};

export function useEvaluationMutations({ selectedDatasetId, onDatasetCreated }: UseEvaluationMutationsOptions) {
    const queryClient = useQueryClient();
    const { showToast } = useSnackbar();

    const [runForm, setRunForm] = useState<RunFormState>({
        prompt_template_key: "",
        prompt_version_id: "",
        variables_json: '{\n  "task": "Summarize the attached knowledge base"\n}',
        retrieval_query: "",
        top_k: "4",
        review_required: false,
    });
    const [reviewNotesById, setReviewNotesById] = useState<Record<string, string>>({});
    const [correctionsById, setCorrectionsById] = useState<Record<string, string>>({});
    const [feedbackCommentByRunId, setFeedbackCommentByRunId] = useState<Record<string, string>>({});
    const [datasetForm, setDatasetForm] = useState<DatasetFormState>({ name: "", description: "" });
    const [datasetCaseForm, setDatasetCaseForm] = useState<DatasetCaseFormState>({
        input_variables_json: '{\n  "task": "What is the return policy?"\n}',
        expected_output_text: "",
        expected_output_json: "",
        notes: "",
    });

    const createRunMutation = useMutation({
        mutationFn: createAiRun,
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["ai"] });
            await queryClient.invalidateQueries({ queryKey: ["ai", "reviews"] });
            showToast({ message: "AI run completed.", severity: "success" });
        },
    });

    const createReviewMutation = useMutation({
        mutationFn: (runId: string) => createAiReview(runId),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["ai", "reviews"] });
            await queryClient.invalidateQueries({ queryKey: ["ai"] });
            showToast({ message: "Review requested.", severity: "success" });
        },
    });

    const decideReviewMutation = useMutation({
        mutationFn: ({
            reviewId,
            status,
            reviewer_notes,
            corrected_output,
        }: {
            reviewId: string;
            status: "approved" | "rejected" | "changes_requested";
            reviewer_notes?: string;
            corrected_output?: string;
        }) => decideAiReview(reviewId, { status, reviewer_notes, corrected_output }),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["ai", "reviews"] });
            await queryClient.invalidateQueries({ queryKey: ["ai"] });
            showToast({ message: "Review decision saved.", severity: "success" });
        },
    });

    const createFeedbackMutation = useMutation({
        mutationFn: ({
            runId,
            rating,
            comment,
            corrected_output,
        }: {
            runId: string;
            rating: -1 | 1;
            comment?: string;
            corrected_output?: string;
        }) => createAiFeedback(runId, { rating, comment, corrected_output }),
        onSuccess: async () => {
            showToast({ message: "Feedback saved.", severity: "success" });
        },
    });

    const createDatasetMutation = useMutation({
        mutationFn: createAiDataset,
        onSuccess: async (dataset) => {
            setDatasetForm({ name: "", description: "" });
            onDatasetCreated?.(dataset.id);
            await queryClient.invalidateQueries({ queryKey: ["ai"] });
            showToast({ message: "Evaluation dataset created.", severity: "success" });
        },
    });

    const createDatasetCaseMutation = useMutation({
        mutationFn: ({
            datasetId,
            payload,
        }: {
            datasetId: string;
            payload: Parameters<typeof createAiDatasetCase>[1];
        }) => createAiDatasetCase(datasetId, payload),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["ai", "dataset-cases", selectedDatasetId] });
            showToast({ message: "Evaluation case added.", severity: "success" });
        },
    });

    const runEvaluationMutation = useMutation({
        mutationFn: ({ datasetId, promptVersionId }: { datasetId: string; promptVersionId: string }) =>
            runAiEvaluation(datasetId, promptVersionId),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["ai", "evaluation-runs"] });
            await queryClient.invalidateQueries({ queryKey: ["ai"] });
            showToast({ message: "Evaluation run completed.", severity: "success" });
        },
    });

    return {
        runForm,
        setRunForm,
        reviewNotesById,
        setReviewNotesById,
        correctionsById,
        setCorrectionsById,
        feedbackCommentByRunId,
        setFeedbackCommentByRunId,
        datasetForm,
        setDatasetForm,
        datasetCaseForm,
        setDatasetCaseForm,
        createRunMutation,
        createReviewMutation,
        decideReviewMutation,
        createFeedbackMutation,
        createDatasetMutation,
        createDatasetCaseMutation,
        runEvaluationMutation,
    };
}
