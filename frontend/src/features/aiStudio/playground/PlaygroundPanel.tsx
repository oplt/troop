import {
    AutoAwesome as AiIcon,
    FolderOpen as ProjectsIcon,
    PlayCircleOutline as RunIcon,
} from "@mui/icons-material";
import { Button, Chip, FormControlLabel, MenuItem, Stack, Switch, TextField } from "@mui/material";
import { Link as RouterLink } from "react-router-dom";

import type { AiDocument, AiRun } from "../../../api/ai";
import { EmptyState } from "../../../components/ui/EmptyState";
import { SectionCard } from "../../../components/ui/SectionCard";
import type { RunFormState, TemplateKeyOption } from "../types";
import { RunResultCard } from "./RunResultCard";

type PlaygroundPanelProps = {
    templateKeyOptions: TemplateKeyOption[];
    documents: AiDocument[];
    recentRuns: AiRun[];
    runForm: RunFormState;
    selectedDocumentIds: string[];
    feedbackCommentByRunId: Record<string, string>;
    correctionsById: Record<string, string>;
    isRunning: boolean;
    onRunFormChange: (updater: (current: RunFormState) => RunFormState) => void;
    onToggleDocument: (documentId: string) => void;
    onRunPrompt: () => void;
    onRequestReview: (runId: string) => void;
    onThumbsUp: (runId: string) => void;
    onThumbsDown: (runId: string) => void;
    onFeedbackCommentChange: (runId: string, value: string) => void;
    onCorrectionChange: (runId: string, value: string) => void;
};

export function PlaygroundPanel({
    templateKeyOptions,
    documents,
    recentRuns,
    runForm,
    selectedDocumentIds,
    feedbackCommentByRunId,
    correctionsById,
    isRunning,
    onRunFormChange,
    onToggleDocument,
    onRunPrompt,
    onRequestReview,
    onThumbsUp,
    onThumbsDown,
    onFeedbackCommentChange,
    onCorrectionChange,
}: PlaygroundPanelProps) {
    return (
        <SectionCard
            title="Run playground"
            description="Execute prompt versions with structured variables, retrieval context, and human-review routing."
        >
            <Stack spacing={2} sx={{ "& > .MuiButton-root": { alignSelf: "flex-start" } }}>
                <TextField
                    select
                    label="Prompt template"
                    value={runForm.prompt_template_key}
                    onChange={(event) =>
                        onRunFormChange((current) => ({ ...current, prompt_template_key: event.target.value }))
                    }
                    fullWidth
                >
                    {templateKeyOptions.map((template) => (
                        <MenuItem key={template.id} value={template.key}>
                            {template.name} ({template.key})
                        </MenuItem>
                    ))}
                </TextField>
                <TextField
                    label="Variables JSON"
                    value={runForm.variables_json}
                    onChange={(event) =>
                        onRunFormChange((current) => ({ ...current, variables_json: event.target.value }))
                    }
                    fullWidth
                    multiline
                    minRows={8}
                />
                <TextField
                    label="Retrieval query"
                    value={runForm.retrieval_query}
                    onChange={(event) =>
                        onRunFormChange((current) => ({ ...current, retrieval_query: event.target.value }))
                    }
                    fullWidth
                />
                <TextField
                    label="Top K chunks"
                    value={runForm.top_k}
                    onChange={(event) => onRunFormChange((current) => ({ ...current, top_k: event.target.value }))}
                    fullWidth
                />
                <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                    {documents.map((document) => (
                        <Chip
                            key={document.id}
                            label={document.title}
                            color={selectedDocumentIds.includes(document.id) ? "primary" : "default"}
                            variant={selectedDocumentIds.includes(document.id) ? "filled" : "outlined"}
                            onClick={() => onToggleDocument(document.id)}
                        />
                    ))}
                </Stack>
                <FormControlLabel
                    control={
                        <Switch
                            checked={runForm.review_required}
                            onChange={(event) =>
                                onRunFormChange((current) => ({ ...current, review_required: event.target.checked }))
                            }
                        />
                    }
                    label="Request human review after this run"
                />
                <Button
                    variant="contained"
                    startIcon={<RunIcon />}
                    disabled={isRunning || !runForm.prompt_template_key}
                    onClick={onRunPrompt}
                >
                    {isRunning ? "Running..." : "Run prompt"}
                </Button>
                {recentRuns.length > 0 ? (
                    <Stack spacing={1.25}>
                        {recentRuns.map((run) => (
                            <RunResultCard
                                key={run.id}
                                run={run}
                                feedbackComment={feedbackCommentByRunId[run.id] ?? ""}
                                correction={correctionsById[run.id] ?? ""}
                                onRequestReview={() => onRequestReview(run.id)}
                                onThumbsUp={() => onThumbsUp(run.id)}
                                onThumbsDown={() => onThumbsDown(run.id)}
                                onFeedbackCommentChange={(value) => onFeedbackCommentChange(run.id, value)}
                                onCorrectionChange={(value) => onCorrectionChange(run.id, value)}
                            />
                        ))}
                    </Stack>
                ) : (
                    <EmptyState
                        icon={<AiIcon />}
                        title="No AI runs yet"
                        description="Run a prompt version here, or open projects to generate work that feeds AI Studio."
                        action={
                            <Button
                                component={RouterLink}
                                to="/projects"
                                variant="contained"
                                size="small"
                                startIcon={<ProjectsIcon />}
                            >
                                Open projects
                            </Button>
                        }
                    />
                )}
            </Stack>
        </SectionCard>
    );
}
