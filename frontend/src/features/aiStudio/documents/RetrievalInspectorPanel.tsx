import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import {
    Accordion,
    AccordionDetails,
    AccordionSummary,
    Alert,
    Box,
    Button,
    Checkbox,
    Chip,
    FormControlLabel,
    Slider,
    Stack,
    TextField,
    Typography,
} from "@mui/material";
import { ExpandMore as ExpandMoreIcon, Search as SearchIcon } from "@mui/icons-material";

import { retrieveAiChunks, type AiDocument } from "../../../api/ai";
import { SectionCard } from "../../../components/ui/SectionCard";
import { extractApiErrorMessage } from "../../../utils/apiErrors";

type RetrievalInspectorPanelProps = {
    documents: AiDocument[];
};

export function RetrievalInspectorPanel({ documents }: RetrievalInspectorPanelProps) {
    const [query, setQuery] = useState("");
    const [documentIds, setDocumentIds] = useState<string[]>([]);
    const [topK, setTopK] = useState(6);
    const retrieval = useMutation({
        mutationFn: () => retrieveAiChunks({ query: query.trim(), document_ids: documentIds, top_k: topK }),
    });

    const toggleDocument = (documentId: string) => {
        setDocumentIds((current) =>
            current.includes(documentId)
                ? current.filter((id) => id !== documentId)
                : [...current, documentId],
        );
    };

    return (
        <Stack spacing={2}>
            <SectionCard
                title="Retrieval inspector"
                description="Test what context the knowledge index returns before using it in a prompt."
            >
                <Stack spacing={2}>
                    <TextField
                        label="Search query"
                        value={query}
                        onChange={(event) => setQuery(event.target.value)}
                        multiline
                        minRows={2}
                        autoFocus
                    />
                    {documents.length > 0 ? (
                        <Box>
                            <Typography variant="subtitle2" gutterBottom>Limit to documents</Typography>
                            <Stack direction="row" flexWrap="wrap" useFlexGap spacing={0.5}>
                                {documents.map((document) => (
                                    <FormControlLabel
                                        key={document.id}
                                        control={
                                            <Checkbox
                                                size="small"
                                                checked={documentIds.includes(document.id)}
                                                onChange={() => toggleDocument(document.id)}
                                            />
                                        }
                                        label={document.title}
                                    />
                                ))}
                            </Stack>
                            <Typography variant="caption" color="text.secondary">
                                With none selected, retrieval searches every indexed document.
                            </Typography>
                        </Box>
                    ) : (
                        <Alert severity="info">Add and index a document before inspecting retrieval.</Alert>
                    )}
                    <Accordion disableGutters elevation={0} sx={{ border: 1, borderColor: "divider" }}>
                        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                            <Typography variant="subtitle2">Advanced retrieval settings</Typography>
                        </AccordionSummary>
                        <AccordionDetails>
                            <Typography variant="body2" gutterBottom>Result limit: {topK}</Typography>
                            <Slider
                                value={topK}
                                onChange={(_, value) => setTopK(value as number)}
                                min={1}
                                max={20}
                                step={1}
                                marks={[{ value: 1, label: "1" }, { value: 20, label: "20" }]}
                                aria-label="Retrieval result limit"
                            />
                        </AccordionDetails>
                    </Accordion>
                    <Button
                        variant="contained"
                        startIcon={<SearchIcon />}
                        disabled={!query.trim() || documents.length === 0 || retrieval.isPending}
                        onClick={() => retrieval.mutate()}
                        sx={{ alignSelf: "flex-start" }}
                    >
                        {retrieval.isPending ? "Searching…" : "Inspect retrieval"}
                    </Button>
                    {retrieval.isError ? (
                        <Alert severity="error">{extractApiErrorMessage(retrieval.error, "Retrieval failed.")}</Alert>
                    ) : null}
                </Stack>
            </SectionCard>

            {retrieval.isSuccess ? (
                <SectionCard
                    title={`Retrieved context (${retrieval.data.length})`}
                    description="Ranked chunks exactly as they are returned to the prompt layer."
                >
                    {retrieval.data.length > 0 ? (
                        <Stack spacing={1.5}>
                            {retrieval.data.map((match, index) => (
                                <Box key={match.chunk_id} sx={{ p: 1.5, border: 1, borderColor: "divider", borderRadius: 1 }}>
                                    <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                                        <Chip size="small" label={`#${index + 1}`} />
                                        <Typography variant="subtitle2">{match.document_title}</Typography>
                                        <Chip size="small" variant="outlined" label={`score ${match.score.toFixed(3)}`} />
                                        <Typography variant="caption" color="text.secondary">Chunk {match.chunk_index + 1}</Typography>
                                    </Stack>
                                    <Typography variant="body2" sx={{ mt: 1, whiteSpace: "pre-wrap" }}>
                                        {match.content}
                                    </Typography>
                                </Box>
                            ))}
                        </Stack>
                    ) : (
                        <Alert severity="info">No matching chunks were returned.</Alert>
                    )}
                </SectionCard>
            ) : null}
        </Stack>
    );
}
