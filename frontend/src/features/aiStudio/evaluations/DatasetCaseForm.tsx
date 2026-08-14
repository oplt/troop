import { Button, MenuItem, Stack, TextField, Typography } from "@mui/material";

import type { AiEvaluationDataset, AiPromptVersion } from "../../../api/ai";
import type { DatasetCaseFormState, DatasetFormState, RunFormState } from "../types";

type DatasetCaseFormProps = {
    datasets: AiEvaluationDataset[];
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

export function DatasetCaseForm({
    datasets,
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
}: DatasetCaseFormProps) {
    return (
        <Stack spacing={1.5}>
            <Typography variant="subtitle2">Evaluation datasets</Typography>
            <TextField
                label="Dataset name"
                value={datasetForm.name}
                onChange={(event) => onDatasetFormChange((current) => ({ ...current, name: event.target.value }))}
                fullWidth
            />
            <TextField
                label="Dataset description"
                value={datasetForm.description}
                onChange={(event) =>
                    onDatasetFormChange((current) => ({ ...current, description: event.target.value }))
                }
                fullWidth
            />
            <Button
                variant="outlined"
                disabled={isCreatingDataset || !datasetForm.name.trim()}
                onClick={onCreateDataset}
            >
                {isCreatingDataset ? "Creating..." : "Create evaluation dataset"}
            </Button>
            <TextField
                select
                label="Selected dataset"
                value={selectedDatasetId}
                onChange={(event) => onSelectedDatasetChange(event.target.value)}
                fullWidth
            >
                {datasets.map((dataset) => (
                    <MenuItem key={dataset.id} value={dataset.id}>
                        {dataset.name}
                    </MenuItem>
                ))}
            </TextField>
            <TextField
                label="Case input variables JSON"
                value={datasetCaseForm.input_variables_json}
                onChange={(event) =>
                    onDatasetCaseFormChange((current) => ({
                        ...current,
                        input_variables_json: event.target.value,
                    }))
                }
                fullWidth
                multiline
                minRows={4}
            />
            <TextField
                label="Expected output text"
                value={datasetCaseForm.expected_output_text}
                onChange={(event) =>
                    onDatasetCaseFormChange((current) => ({
                        ...current,
                        expected_output_text: event.target.value,
                    }))
                }
                fullWidth
                multiline
                minRows={2}
            />
            <TextField
                label="Expected output JSON"
                value={datasetCaseForm.expected_output_json}
                onChange={(event) =>
                    onDatasetCaseFormChange((current) => ({
                        ...current,
                        expected_output_json: event.target.value,
                    }))
                }
                fullWidth
                multiline
                minRows={2}
            />
            <TextField
                label="Notes"
                value={datasetCaseForm.notes}
                onChange={(event) =>
                    onDatasetCaseFormChange((current) => ({ ...current, notes: event.target.value }))
                }
                fullWidth
            />
            <Button variant="outlined" disabled={isCreatingCase || !selectedDatasetId} onClick={onAddDatasetCase}>
                {isCreatingCase ? "Saving..." : "Add dataset case"}
            </Button>
            <TextField
                select
                label="Prompt version for evaluation"
                value={runForm.prompt_version_id}
                onChange={(event) =>
                    onRunFormChange((current) => ({ ...current, prompt_version_id: event.target.value }))
                }
                fullWidth
            >
                {templateVersions.map((version) => (
                    <MenuItem key={version.id} value={version.id}>
                        v{version.version_number} • {version.model_name}
                    </MenuItem>
                ))}
            </TextField>
            <Button
                variant="contained"
                disabled={isRunningEvaluation || !selectedDatasetId || !runForm.prompt_version_id}
                onClick={onRunEvaluation}
            >
                {isRunningEvaluation ? "Evaluating..." : "Run evaluation"}
            </Button>
        </Stack>
    );
}
