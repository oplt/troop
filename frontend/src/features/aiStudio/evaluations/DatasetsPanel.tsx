import { Box, Stack, Typography } from "@mui/material";

import type {
    AiEvaluationCase,
    AiEvaluationDataset,
    AiEvaluationRun,
    AiPromptVersion,
} from "../../../api/ai";
import { SectionCard } from "../../../components/ui/SectionCard";
import { compactDocumentRowSx } from "../styles";
import type { DatasetCaseFormState, DatasetFormState, RunFormState } from "../types";
import { DatasetCaseForm } from "./DatasetCaseForm";
import { EvaluationResults } from "./EvaluationResults";

type DatasetsPanelProps = {
    datasets: AiEvaluationDataset[];
    datasetCases: AiEvaluationCase[];
    evaluationRuns: AiEvaluationRun[];
    templateVersions: AiPromptVersion[];
    datasetForm: DatasetFormState;
    datasetCaseForm: DatasetCaseFormState;
    selectedDatasetId: string;
    runForm: RunFormState;
    isCreatingDataset: boolean;
    isCreatingCase: boolean;
    isRunningEvaluation: boolean;
    onDatasetFormChange: (updater: (current: DatasetFormState) => DatasetFormState) => void;
    onDatasetCaseFormChange: (updater: (current: DatasetCaseFormState) => DatasetCaseFormState) => void;
    onSelectedDatasetChange: (datasetId: string) => void;
    onRunFormChange: (updater: (current: RunFormState) => RunFormState) => void;
    onCreateDataset: () => void;
    onAddDatasetCase: () => void;
    onRunEvaluation: () => void;
};

export function DatasetsPanel({
    datasets,
    datasetCases,
    evaluationRuns,
    templateVersions,
    datasetForm,
    datasetCaseForm,
    selectedDatasetId,
    runForm,
    isCreatingDataset,
    isCreatingCase,
    isRunningEvaluation,
    onDatasetFormChange,
    onDatasetCaseFormChange,
    onSelectedDatasetChange,
    onRunFormChange,
    onCreateDataset,
    onAddDatasetCase,
    onRunEvaluation,
}: DatasetsPanelProps) {
    return (
        <SectionCard
            title="Evaluation datasets"
            description="Reusable benchmark datasets for prompt regression testing."
        >
            <Stack spacing={1.5}>
                <DatasetCaseForm
                    datasets={datasets}
                    templateVersions={templateVersions}
                    datasetForm={datasetForm}
                    datasetCaseForm={datasetCaseForm}
                    selectedDatasetId={selectedDatasetId}
                    runForm={runForm}
                    isCreatingDataset={isCreatingDataset}
                    isCreatingCase={isCreatingCase}
                    isRunningEvaluation={isRunningEvaluation}
                    onDatasetFormChange={onDatasetFormChange}
                    onDatasetCaseFormChange={onDatasetCaseFormChange}
                    onSelectedDatasetChange={onSelectedDatasetChange}
                    onRunFormChange={onRunFormChange}
                    onCreateDataset={onCreateDataset}
                    onAddDatasetCase={onAddDatasetCase}
                    onRunEvaluation={onRunEvaluation}
                />
                {datasetCases.length > 0 && (
                    <Stack spacing={1}>
                        {datasetCases.map((item) => (
                            <Box key={item.id} sx={compactDocumentRowSx}>
                                <Typography variant="body2" sx={{ fontFamily: '"IBM Plex Mono", monospace' }}>
                                    {JSON.stringify(item.input_variables)}
                                </Typography>
                                {item.expected_output_text && (
                                    <Typography variant="caption" color="text.secondary">
                                        Expected: {item.expected_output_text}
                                    </Typography>
                                )}
                            </Box>
                        ))}
                    </Stack>
                )}
                <EvaluationResults evaluationRuns={evaluationRuns} />
            </Stack>
        </SectionCard>
    );
}
