import { Description as DocumentIcon } from "@mui/icons-material";
import { Box, Chip, Stack, Typography } from "@mui/material";

import type { AiDocument } from "../../../api/ai";
import { EmptyState } from "../../../components/ui/EmptyState";
import { SectionCard } from "../../../components/ui/SectionCard";
import { formatDateTime } from "../../../utils/formatters";
import { compactDocumentRowSx } from "../styles";
import type { TextDocumentFormState } from "../types";
import { DocumentUploadForm } from "./DocumentUploadForm";

type DocumentsPanelProps = {
    documents: AiDocument[];
    textDocumentForm: TextDocumentFormState;
    uploadDescription: string;
    isCreatingText: boolean;
    isUploading: boolean;
    onTextDocumentFormChange: (updater: (current: TextDocumentFormState) => TextDocumentFormState) => void;
    onUploadDescriptionChange: (value: string) => void;
    onCreateTextDocument: () => void;
    onUploadFile: (file: File) => void;
};

export function DocumentsPanel({
    documents,
    textDocumentForm,
    uploadDescription,
    isCreatingText,
    isUploading,
    onTextDocumentFormChange,
    onUploadDescriptionChange,
    onCreateTextDocument,
    onUploadFile,
}: DocumentsPanelProps) {
    return (
        <SectionCard
            title="Retrieval documents"
            description="Ingest source files or direct text, chunk them, and use them as retrieval context in prompt runs."
        >
            <Stack spacing={2}>
                <DocumentUploadForm
                    textDocumentForm={textDocumentForm}
                    uploadDescription={uploadDescription}
                    isCreatingText={isCreatingText}
                    isUploading={isUploading}
                    onTextDocumentFormChange={onTextDocumentFormChange}
                    onUploadDescriptionChange={onUploadDescriptionChange}
                    onCreateTextDocument={onCreateTextDocument}
                    onUploadFile={onUploadFile}
                />
                {documents.length > 0 ? (
                    <Stack spacing={1}>
                        {documents.map((document) => (
                            <Box key={document.id} sx={compactDocumentRowSx}>
                                <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                                    <Typography variant="subtitle2">{document.title}</Typography>
                                    {document.ingestion_status !== "completed" ? (
                                        <Chip
                                            size="small"
                                            label={document.ingestion_status}
                                            color={
                                                document.ingestion_status === "failed"
                                                    ? "error"
                                                    : document.ingestion_status === "running"
                                                      ? "info"
                                                      : "warning"
                                            }
                                            variant="outlined"
                                        />
                                    ) : null}
                                </Stack>
                                <Typography variant="caption" color="text.secondary">
                                    {document.chunk_count} chunks • {document.content_type} •{" "}
                                    {formatDateTime(document.updated_at)}
                                </Typography>
                            </Box>
                        ))}
                    </Stack>
                ) : (
                    <EmptyState
                        icon={<DocumentIcon />}
                        title="No documents indexed"
                        description="Upload source material to power retrieval-augmented runs."
                    />
                )}
            </Stack>
        </SectionCard>
    );
}
