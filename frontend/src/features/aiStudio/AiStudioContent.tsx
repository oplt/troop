import { useAiStudioOverview } from "./hooks/useAiStudioOverview";
import { useDocumentMutations } from "./hooks/useDocumentMutations";
import { useEvaluationMutations } from "./hooks/useEvaluationMutations";
import { usePromptMutations } from "./hooks/usePromptMutations";
import { Stack } from "@mui/material";

import type { AiOverview } from "../../api/ai";
import { useSnackbar } from "../../app/snackbarContext";
import { PageHeader } from "../../components/ui/PageHeader";
import { PageShell } from "../../components/ui/PageShell";
import { AiStudioOverview } from "./AiStudioOverview";
import { AiSectionPanel, AiStudioTabs } from "./AiStudioTabs";
import { DatasetsPanel } from "./evaluations/DatasetsPanel";
import { DocumentsPanel } from "./documents/DocumentsPanel";
import { parseVariableDefinitions } from "./formatUtils";
import { parseJsonObject } from "./formUtils";
import { PlaygroundPanel } from "./playground/PlaygroundPanel";
import { PromptTemplatesPanel } from "./prompts/PromptTemplatesPanel";
import { ReviewQueue } from "./reviews/ReviewQueue";
import { templateKeyOptions } from "./types";
import { PromptVersionsPanel } from "./versions/PromptVersionsPanel";

type AiStudioContentProps = {
    overview: AiOverview;
};

export function AiStudioContent({ overview }: AiStudioContentProps) {
    const { showToast } = useSnackbar();
    const studio = useAiStudioOverview(overview);
    const prompts = usePromptMutations({ selectedTemplateId: studio.selectedTemplateId });
    const documents = useDocumentMutations();
    const evaluations = useEvaluationMutations({
        selectedDatasetId: studio.selectedDatasetId,
        onDatasetCreated: studio.setSelectedDatasetId,
    });

    return (
        <PageShell maxWidth="xl">
            <PageHeader
                title="AI Studio"
                description="Prompt templates, playground runs, retrieval documents, and human reviews."
            />

            <AiStudioOverview
                promptTemplateCount={studio.promptTemplates.length}
                documentCount={studio.documents.length}
                pendingReviewCount={studio.reviews.filter((item) => item.status === "pending").length}
                datasetCount={studio.datasets.length}
            />

            <AiStudioTabs activeSection={studio.activeSection} onSectionChange={studio.setActiveSection}>
                <Stack spacing={2}>
                    <AiSectionPanel activeSection={studio.activeSection} value="prompts">
                        <PromptTemplatesPanel
                            templates={studio.promptTemplates}
                            templateForm={prompts.templateForm}
                            selectedTemplateId={studio.selectedTemplateId}
                            isCreating={prompts.createTemplateMutation.isPending}
                            onTemplateFormChange={prompts.setTemplateForm}
                            onCreateTemplate={() => prompts.createTemplateMutation.mutate(prompts.templateForm)}
                            onSelectTemplate={studio.setSelectedTemplateId}
                        />
                    </AiSectionPanel>

                    <AiSectionPanel activeSection={studio.activeSection} value="playground">
                        <PlaygroundPanel
                            templateKeyOptions={templateKeyOptions(studio.promptTemplates)}
                            documents={studio.documents}
                            recentRuns={studio.recentRuns}
                            runForm={evaluations.runForm}
                            selectedDocumentIds={studio.selectedDocumentIds}
                            feedbackCommentByRunId={evaluations.feedbackCommentByRunId}
                            correctionsById={evaluations.correctionsById}
                            isRunning={evaluations.createRunMutation.isPending}
                            onRunFormChange={evaluations.setRunForm}
                            onToggleDocument={studio.toggleDocument}
                            onRunPrompt={() => {
                                try {
                                    evaluations.createRunMutation.mutate({
                                        prompt_template_key: evaluations.runForm.prompt_template_key,
                                        variables: parseJsonObject(evaluations.runForm.variables_json),
                                        retrieval_query: evaluations.runForm.retrieval_query || undefined,
                                        document_ids: studio.selectedDocumentIds,
                                        top_k: Number(evaluations.runForm.top_k || 4),
                                        review_required: evaluations.runForm.review_required,
                                    });
                                } catch (error) {
                                    showToast({
                                        message: error instanceof Error ? error.message : "Invalid variables JSON.",
                                        severity: "error",
                                    });
                                }
                            }}
                            onRequestReview={(runId) => evaluations.createReviewMutation.mutate(runId)}
                            onThumbsUp={(runId) =>
                                evaluations.createFeedbackMutation.mutate({
                                    runId,
                                    rating: 1,
                                    comment: evaluations.feedbackCommentByRunId[runId],
                                })
                            }
                            onThumbsDown={(runId) =>
                                evaluations.createFeedbackMutation.mutate({
                                    runId,
                                    rating: -1,
                                    comment: evaluations.feedbackCommentByRunId[runId],
                                    corrected_output: evaluations.correctionsById[runId],
                                })
                            }
                            onFeedbackCommentChange={(runId, value) =>
                                evaluations.setFeedbackCommentByRunId((current) => ({ ...current, [runId]: value }))
                            }
                            onCorrectionChange={(runId, value) =>
                                evaluations.setCorrectionsById((current) => ({ ...current, [runId]: value }))
                            }
                        />
                    </AiSectionPanel>

                    <AiSectionPanel activeSection={studio.activeSection} value="versions">
                        <PromptVersionsPanel
                            templates={studio.promptTemplates}
                            providers={studio.providers}
                            versions={studio.selectedTemplateVersions}
                            selectedTemplateId={studio.selectedTemplateId}
                            versionForm={prompts.versionForm}
                            isCreating={prompts.createVersionMutation.isPending}
                            onSelectedTemplateChange={studio.setSelectedTemplateId}
                            onVersionFormChange={prompts.setVersionForm}
                            onCreateVersion={() =>
                                prompts.createVersionMutation.mutate({
                                    templateId: studio.selectedTemplateId,
                                    payload: {
                                        provider_key: prompts.versionForm.provider_key,
                                        model_name: prompts.versionForm.model_name,
                                        system_prompt: prompts.versionForm.system_prompt,
                                        user_prompt_template: prompts.versionForm.user_prompt_template,
                                        variable_definitions: parseVariableDefinitions(prompts.versionForm.variable_names),
                                        response_format: prompts.versionForm.response_format,
                                        temperature: Number(prompts.versionForm.temperature || 0.2),
                                        rollout_percentage: Number(prompts.versionForm.rollout_percentage || 100),
                                        is_published: prompts.versionForm.is_published,
                                        input_cost_per_million: Number(prompts.versionForm.input_cost_per_million || 0),
                                        output_cost_per_million: Number(prompts.versionForm.output_cost_per_million || 0),
                                    },
                                })
                            }
                            onActivateVersion={(versionId) =>
                                prompts.activateVersionMutation.mutate({
                                    templateId: studio.selectedTemplateId,
                                    versionId,
                                })
                            }
                            onTogglePublish={(versionId, isPublished) =>
                                prompts.publishVersionMutation.mutate({
                                    templateId: studio.selectedTemplateId,
                                    versionId,
                                    isPublished,
                                })
                            }
                        />
                    </AiSectionPanel>

                    <AiSectionPanel activeSection={studio.activeSection} value="documents">
                        <DocumentsPanel
                            documents={studio.documents}
                            textDocumentForm={documents.textDocumentForm}
                            uploadDescription={documents.uploadDescription}
                            isCreatingText={documents.createTextDocumentMutation.isPending}
                            isUploading={documents.uploadDocumentMutation.isPending}
                            onTextDocumentFormChange={documents.setTextDocumentForm}
                            onUploadDescriptionChange={documents.setUploadDescription}
                            onCreateTextDocument={() => documents.createTextDocumentMutation.mutate(documents.textDocumentForm)}
                            onUploadFile={(file) =>
                                documents.uploadDocumentMutation.mutate({
                                    file,
                                    description: documents.uploadDescription || undefined,
                                })
                            }
                        />
                    </AiSectionPanel>

                    <AiSectionPanel activeSection={studio.activeSection} value="reviews">
                        <ReviewQueue
                            reviews={studio.reviews}
                            reviewNotesById={evaluations.reviewNotesById}
                            correctionsById={evaluations.correctionsById}
                            onReviewNotesChange={(reviewId, value) =>
                                evaluations.setReviewNotesById((current) => ({ ...current, [reviewId]: value }))
                            }
                            onCorrectionChange={(reviewId, value) =>
                                evaluations.setCorrectionsById((current) => ({ ...current, [reviewId]: value }))
                            }
                            onApprove={(reviewId) =>
                                evaluations.decideReviewMutation.mutate({
                                    reviewId,
                                    status: "approved",
                                    reviewer_notes: evaluations.reviewNotesById[reviewId],
                                    corrected_output: evaluations.correctionsById[reviewId],
                                })
                            }
                            onRequestChanges={(reviewId) =>
                                evaluations.decideReviewMutation.mutate({
                                    reviewId,
                                    status: "changes_requested",
                                    reviewer_notes: evaluations.reviewNotesById[reviewId],
                                    corrected_output: evaluations.correctionsById[reviewId],
                                })
                            }
                            onReject={(reviewId) =>
                                evaluations.decideReviewMutation.mutate({
                                    reviewId,
                                    status: "rejected",
                                    reviewer_notes: evaluations.reviewNotesById[reviewId],
                                })
                            }
                        />
                    </AiSectionPanel>

                    <AiSectionPanel activeSection={studio.activeSection} value="datasets">
                        <DatasetsPanel
                            datasets={studio.datasets}
                            datasetCases={studio.selectedDatasetCases}
                            evaluationRuns={studio.evaluationRuns}
                            templateVersions={studio.selectedTemplateVersions}
                            datasetForm={evaluations.datasetForm}
                            datasetCaseForm={evaluations.datasetCaseForm}
                            selectedDatasetId={studio.selectedDatasetId}
                            runForm={evaluations.runForm}
                            isCreatingDataset={evaluations.createDatasetMutation.isPending}
                            isCreatingCase={evaluations.createDatasetCaseMutation.isPending}
                            isRunningEvaluation={evaluations.runEvaluationMutation.isPending}
                            onDatasetFormChange={evaluations.setDatasetForm}
                            onDatasetCaseFormChange={evaluations.setDatasetCaseForm}
                            onSelectedDatasetChange={studio.setSelectedDatasetId}
                            onRunFormChange={evaluations.setRunForm}
                            onCreateDataset={() => evaluations.createDatasetMutation.mutate(evaluations.datasetForm)}
                            onAddDatasetCase={() => {
                                try {
                                    evaluations.createDatasetCaseMutation.mutate({
                                        datasetId: studio.selectedDatasetId,
                                        payload: {
                                            input_variables: parseJsonObject(evaluations.datasetCaseForm.input_variables_json),
                                            expected_output_text: evaluations.datasetCaseForm.expected_output_text || null,
                                            expected_output_json: evaluations.datasetCaseForm.expected_output_json.trim()
                                                ? parseJsonObject(evaluations.datasetCaseForm.expected_output_json)
                                                : null,
                                            notes: evaluations.datasetCaseForm.notes || null,
                                        },
                                    });
                                } catch (error) {
                                    showToast({
                                        message: error instanceof Error ? error.message : "Invalid dataset case JSON.",
                                        severity: "error",
                                    });
                                }
                            }}
                            onRunEvaluation={() =>
                                evaluations.runEvaluationMutation.mutate({
                                    datasetId: studio.selectedDatasetId,
                                    promptVersionId: evaluations.runForm.prompt_version_id,
                                })
                            }
                        />
                    </AiSectionPanel>
                </Stack>
            </AiStudioTabs>
        </PageShell>
    );
}
