import { Button, Stack, TextField } from "@mui/material";

import type { TextDocumentFormState } from "../types";

type DocumentUploadFormProps = {
    textDocumentForm: TextDocumentFormState;
    uploadDescription: string;
    isCreatingText: boolean;
    isUploading: boolean;
    onTextDocumentFormChange: (updater: (current: TextDocumentFormState) => TextDocumentFormState) => void;
    onUploadDescriptionChange: (value: string) => void;
    onCreateTextDocument: () => void;
    onUploadFile: (file: File) => void;
};

export function DocumentUploadForm({
    textDocumentForm,
    uploadDescription,
    isCreatingText,
    isUploading,
    onTextDocumentFormChange,
    onUploadDescriptionChange,
    onCreateTextDocument,
    onUploadFile,
}: DocumentUploadFormProps) {
    return (
        <Stack spacing={2} sx={{ "& > .MuiButton-root": { alignSelf: "flex-start" } }}>
            <TextField
                label="Document title"
                value={textDocumentForm.title}
                onChange={(event) =>
                    onTextDocumentFormChange((current) => ({ ...current, title: event.target.value }))
                }
                fullWidth
            />
            <TextField
                label="Description"
                value={textDocumentForm.description}
                onChange={(event) =>
                    onTextDocumentFormChange((current) => ({ ...current, description: event.target.value }))
                }
                fullWidth
            />
            <TextField
                label="Document content"
                value={textDocumentForm.content}
                onChange={(event) =>
                    onTextDocumentFormChange((current) => ({ ...current, content: event.target.value }))
                }
                fullWidth
                multiline
                minRows={6}
            />
            <Button
                variant="outlined"
                disabled={isCreatingText || !textDocumentForm.title.trim() || !textDocumentForm.content.trim()}
                onClick={onCreateTextDocument}
            >
                {isCreatingText ? "Queueing..." : "Create text document"}
            </Button>
            <Button component="label" variant="contained" disabled={isUploading}>
                {isUploading ? "Uploading..." : "Upload text/markdown/json file"}
                <input
                    hidden
                    type="file"
                    accept=".txt,.md,.json,.ndjson,text/plain,text/markdown,application/json"
                    onChange={(event) => {
                        const file = event.target.files?.[0];
                        if (file) {
                            onUploadFile(file);
                        }
                        event.currentTarget.value = "";
                    }}
                />
            </Button>
            <TextField
                label="Upload description"
                value={uploadDescription}
                onChange={(event) => onUploadDescriptionChange(event.target.value)}
                fullWidth
            />
        </Stack>
    );
}
