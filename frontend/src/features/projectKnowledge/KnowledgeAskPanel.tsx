import { useEffect, useRef, useState } from "react";
import {
    Alert,
    Button,
    Chip,
    Collapse,
    FormControlLabel,
    LinearProgress,
    Paper,
    Stack,
    Switch,
    TextField,
    Typography,
} from "@mui/material";

import {
    answerRag,
    searchRag,
    streamRagAnswer,
    type RagAnswer,
    type RagChunkMatch,
    type RagCitation,
} from "../../api/rag";
import { SectionCard } from "../../components/ui/SectionCard";
import { extractApiErrorMessage } from "../../utils/apiErrors";

export function KnowledgeAskPanel({ projectId }: { projectId: string }) {
    const [query, setQuery] = useState("");
    const [answer, setAnswer] = useState("");
    const [citations, setCitations] = useState<RagCitation[]>([]);
    const [matches, setMatches] = useState<RagChunkMatch[]>([]);
    const [isWorking, setIsWorking] = useState(false);
    const [streamEnabled, setStreamEnabled] = useState(false);
    const [inspectorOpen, setInspectorOpen] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [answerMeta, setAnswerMeta] = useState<Pick<RagAnswer, "context_found" | "grounded" | "model"> | null>(null);
    const controllerRef = useRef<AbortController | null>(null);

    useEffect(() => () => controllerRef.current?.abort(), []);

    const ask = async () => {
        const trimmed = query.trim();
        if (!trimmed) return;
        controllerRef.current?.abort();
        const controller = new AbortController();
        controllerRef.current = controller;
        setIsWorking(true);
        setAnswer("");
        setCitations([]);
        setMatches([]);
        setError(null);
        setAnswerMeta(null);
        try {
            const payload = { query: trimmed, top_k: 5, include_decisions: true };
            if (!streamEnabled) {
                const result = await answerRag(projectId, payload);
                setAnswer(result.answer);
                setCitations(result.citations);
                setAnswerMeta(result);
                return;
            }
            await streamRagAnswer(projectId, payload, {
                signal: controller.signal,
                onEvent: (event) => {
                    if (event.type === "meta") setCitations(event.citations ?? []);
                    if (event.type === "token") setAnswer((current) => current + event.text);
                    if (event.type === "done") {
                        setAnswer((current) => event.answer || current);
                        if (event.citations) setCitations(event.citations);
                        setAnswerMeta({
                            context_found: event.context_found,
                            grounded: event.grounded,
                            model: event.model,
                        });
                    }
                },
            });
        } catch (caught) {
            if (!(caught instanceof DOMException && caught.name === "AbortError")) {
                setError(extractApiErrorMessage(caught, "Could not answer from project knowledge."));
            }
        } finally {
            if (controllerRef.current === controller) {
                controllerRef.current = null;
                setIsWorking(false);
            }
        }
    };

    const inspectRetrieval = async () => {
        if (!query.trim()) return;
        setInspectorOpen(true);
        setError(null);
        try {
            setMatches(await searchRag(projectId, { query: query.trim(), top_k: 8, include_decisions: true }));
        } catch (caught) {
            setError(extractApiErrorMessage(caught, "Could not inspect retrieval."));
        }
    };

    return (
        <Stack spacing={2}>
            <SectionCard title="Ask project knowledge" description="Answers are grounded in this project's indexed sources.">
                <Stack spacing={1.5}>
                    <TextField
                        label="Question"
                        value={query}
                        onChange={(event) => setQuery(event.target.value)}
                        onKeyDown={(event) => {
                            if (event.key === "Enter" && !event.shiftKey) {
                                event.preventDefault();
                                void ask();
                            }
                        }}
                        multiline
                        minRows={2}
                        placeholder="What constraints should the team account for?"
                        fullWidth
                    />
                    <Stack direction={{ xs: "column", sm: "row" }} spacing={1} alignItems={{ sm: "center" }}>
                        <Button variant="contained" disabled={!query.trim() || isWorking} onClick={() => void ask()}>
                            {isWorking ? "Answering…" : "Ask"}
                        </Button>
                        {isWorking && streamEnabled ? (
                            <Button onClick={() => controllerRef.current?.abort()}>Stop</Button>
                        ) : null}
                        <FormControlLabel
                            control={<Switch checked={streamEnabled} onChange={(_, checked) => setStreamEnabled(checked)} />}
                            label="Stream answer"
                        />
                    </Stack>
                    {isWorking ? <LinearProgress /> : null}
                    {error ? <Alert severity="error">{error}</Alert> : null}
                </Stack>
            </SectionCard>

            {answer ? (
                <SectionCard
                    title="Answer"
                    action={answerMeta ? (
                        <Stack direction="row" spacing={0.75}>
                            <Chip size="small" label={answerMeta.context_found ? "Context found" : "No context"} />
                            {answerMeta.model ? <Chip size="small" variant="outlined" label={answerMeta.model} /> : null}
                        </Stack>
                    ) : null}
                >
                    <Typography sx={{ whiteSpace: "pre-wrap" }}>{answer}</Typography>
                    {citations.length > 0 ? (
                        <Stack spacing={1} sx={{ mt: 3 }}>
                            <Typography variant="subtitle2">Sources</Typography>
                            {citations.map((citation) => (
                                <Paper key={citation.chunk_id} variant="outlined" sx={{ p: 1.5, borderRadius: 1 }}>
                                    <Stack direction="row" justifyContent="space-between" spacing={1}>
                                        <Typography variant="subtitle2">[{citation.source_index}] {citation.title}</Typography>
                                        <Chip size="small" variant="outlined" label={`${Math.round(citation.score * 100)}%`} />
                                    </Stack>
                                    <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
                                        {citation.excerpt}
                                    </Typography>
                                </Paper>
                            ))}
                        </Stack>
                    ) : null}
                </SectionCard>
            ) : null}

            <SectionCard density="plain">
                <Button variant="text" onClick={() => (inspectorOpen ? setInspectorOpen(false) : void inspectRetrieval())}>
                    {inspectorOpen ? "Hide retrieval inspection" : "Inspect retrieval"}
                </Button>
                <Collapse in={inspectorOpen}>
                    <Stack spacing={1} sx={{ mt: 1 }}>
                        {matches.length === 0 ? (
                            <Typography variant="body2" color="text.secondary">No retrieved chunks to inspect.</Typography>
                        ) : matches.map((match) => (
                            <Paper key={match.chunk_id} variant="outlined" sx={{ p: 1.5, borderRadius: 1 }}>
                                <Stack direction="row" justifyContent="space-between" spacing={1}>
                                    <Typography variant="subtitle2">{match.title} · chunk {match.chunk_index}</Typography>
                                    <Chip size="small" label={match.score.toFixed(3)} />
                                </Stack>
                                <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
                                    {match.content}
                                </Typography>
                            </Paper>
                        ))}
                    </Stack>
                </Collapse>
            </SectionCard>
        </Stack>
    );
}
