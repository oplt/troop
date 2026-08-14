import {
    Alert,
    Box,
    Button,
    Chip,
    CircularProgress,
    Stack,
    TextField,
    Typography,
} from "@mui/material";
import { AutoAwesome } from "@mui/icons-material";
import { useState } from "react";
import type { WorkflowGenerateResponse, WorkflowScaffoldGap } from "../../api/workforce";
import { humanizeKey } from "../../utils/formatters";

const GAP_LABELS: Record<WorkflowScaffoldGap["kind"], string> = {
    missing_connection: "Missing connection",
    missing_scope: "Missing scope",
    missing_approval_step: "Needs approval step",
    unavailable_operation: "Unavailable operation",
    missing_agent: "Missing agent",
};

type WorkflowScaffoldPanelProps = {
    onGenerate: (prompt: string) => Promise<WorkflowGenerateResponse>;
    onApply: (result: WorkflowGenerateResponse) => void;
    onFocusNode?: (nodeId: string) => void;
    busy?: boolean;
};

export function WorkflowScaffoldPanel({
    onGenerate,
    onApply,
    onFocusNode,
    busy = false,
}: WorkflowScaffoldPanelProps) {
    const [prompt, setPrompt] = useState("");
    const [result, setResult] = useState<WorkflowGenerateResponse | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [generating, setGenerating] = useState(false);

    const handleGenerate = async () => {
        const trimmed = prompt.trim();
        if (trimmed.length < 3) {
            setError("Describe the workflow in at least a few words.");
            return;
        }
        setGenerating(true);
        setError(null);
        try {
            const response = await onGenerate(trimmed);
            setResult(response);
        } catch (err) {
            setResult(null);
            setError(err instanceof Error ? err.message : "Generation failed.");
        } finally {
            setGenerating(false);
        }
    };

    return (
        <Stack spacing={2}>
            <Typography variant="subtitle2">Describe the workflow you want</Typography>
            <Typography variant="body2" color="text.secondary">
                AI proposes a typed draft using your installed connectors only. Review gaps, test, then publish explicitly.
            </Typography>
            <TextField
                label="Workflow goal"
                placeholder="When a new Gmail arrives, classify it, draft a reply, and send after Telegram approval"
                value={prompt}
                onChange={(event) => setPrompt(event.target.value)}
                multiline
                minRows={3}
                fullWidth
                size="small"
            />
            <Button
                variant="contained"
                startIcon={generating ? <CircularProgress size={16} color="inherit" /> : <AutoAwesome />}
                onClick={handleGenerate}
                disabled={generating || busy}
            >
                Generate draft
            </Button>
            {error && <Alert severity="error">{error}</Alert>}
            {result && (
                <Stack spacing={1.5}>
                    <Alert severity={result.validation.valid ? "success" : "warning"}>
                        {result.summary}
                    </Alert>
                    <Typography variant="caption" color="text.secondary">
                        Mode: {humanizeKey(result.provenance.generation_mode)} · Draft saved · not published
                    </Typography>
                    {result.gaps.length > 0 && (
                        <Box>
                            <Typography variant="subtitle2" gutterBottom>
                                Configuration gaps ({result.gaps.length})
                            </Typography>
                            <Stack spacing={1}>
                                {result.gaps.map((gap, index) => (
                                    <Alert
                                        key={`${gap.kind}-${gap.node_id ?? index}`}
                                        severity="info"
                                        action={
                                            gap.node_id && onFocusNode ? (
                                                <Button color="inherit" size="small" onClick={() => onFocusNode(gap.node_id!)}>
                                                    Focus
                                                </Button>
                                            ) : undefined
                                        }
                                    >
                                        <Stack spacing={0.5}>
                                            <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                                                <Chip size="small" label={GAP_LABELS[gap.kind]} />
                                                {gap.provider_slug && (
                                                    <Chip size="small" variant="outlined" label={gap.provider_slug} />
                                                )}
                                            </Stack>
                                            <Typography variant="body2">{gap.message}</Typography>
                                            {gap.remediation && (
                                                <Typography variant="caption" color="text.secondary">
                                                    {gap.remediation}
                                                </Typography>
                                            )}
                                        </Stack>
                                    </Alert>
                                ))}
                            </Stack>
                        </Box>
                    )}
                    <Button variant="outlined" onClick={() => onApply(result)} disabled={busy}>
                        Load draft on canvas
                    </Button>
                </Stack>
            )}
        </Stack>
    );
}
