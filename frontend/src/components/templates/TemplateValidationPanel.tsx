import { Alert, Button, Paper, Stack, Typography } from "@mui/material";
import { CloudUpload as UploadIcon } from "@mui/icons-material";

type TemplateValidationPanelProps = {
    validationError: string | null;
    validationWarnings: string[];
    createAgentError: string | null;
    isCreatingAgent: boolean;
    onCreateAgent: () => void;
    onImportMarkdown: (file: File) => Promise<void> | void;
};

export function TemplateValidationPanel({
    validationError,
    validationWarnings,
    createAgentError,
    isCreatingAgent,
    onCreateAgent,
    onImportMarkdown,
}: TemplateValidationPanelProps) {
    return (
        <Paper sx={{ p: 2, borderRadius: 4 }}>
            <Stack spacing={2}>
                <Typography variant="subtitle2">Validation + save</Typography>
                {createAgentError && <Alert severity="error">{createAgentError}</Alert>}
                {validationError && <Alert severity="error">{validationError}</Alert>}
                {validationWarnings.length > 0 && <Alert severity="warning">{validationWarnings.join(" ")}</Alert>}
                <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5}>
                    <Button variant="contained" onClick={onCreateAgent} disabled={isCreatingAgent}>
                        Save agent
                    </Button>
                    <Button variant="outlined" component="label" startIcon={<UploadIcon />}>
                        Import markdown
                        <input
                            hidden
                            type="file"
                            accept=".md,text/markdown"
                            onChange={(event) => {
                                const file = event.target.files?.[0];
                                if (file) void onImportMarkdown(file);
                            }}
                        />
                    </Button>
                </Stack>
            </Stack>
        </Paper>
    );
}
