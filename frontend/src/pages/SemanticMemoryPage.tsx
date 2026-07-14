import { useMemo, useState } from "react";
import { Link as RouterLink, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
    Alert,
    Box,
    Button,
    Chip,
    Dialog,
    DialogActions,
    DialogContent,
    DialogTitle,
    FormControlLabel,
    IconButton,
    Link,
    MenuItem,
    Paper,
    Stack,
    Switch,
    Table,
    TableBody,
    TableCell,
    TableContainer,
    TableHead,
    TableRow,
    TextField,
    Tooltip,
    Typography,
} from "@mui/material";
import { InfoOutlined as InfoOutlinedIcon } from "@mui/icons-material";
import {
    createSemanticMemory,
    decideApproval,
    getOrchestrationProject,
    getProjectMemorySettings,
    getRunWorkingMemory,
    isPendingSemanticWrite,
    listApprovals,
    listEpisodicArchives,
    listProceduralPlaybooks,
    listRuns,
    listSemanticMemory,
    listSemanticMemoryConflicts,
    mergeSemanticMemoryEntries,
    patchProjectMemorySettings,
    reindexEpisodicMemory,
    searchEpisodicMemory,
    type Approval,
    type SemanticMemoryEntry,
} from "../api/orchestration";
import { CollapsibleSectionCard } from "../components/ui/CollapsibleSectionCard";
import { PageShell } from "../components/ui/PageShell";
import { SectionCard } from "../components/ui/SectionCard";
import { formatDateTime } from "../utils/formatters";
import { useDebounce } from "../hooks/useDebounce";
import { queryKeys } from "../config/queryKeys";
import { useSnackbar } from "../app/snackbarContext";
import { extractApiErrorMessage } from "../utils/apiErrors";
import { EmptyState } from "../components/ui/EmptyState";
import { ErrorOutline as ErrorOutlineIcon, Refresh as RefreshIcon } from "@mui/icons-material";

const ENTRY_TYPES = ["note", "policy", "standard", "adr", "glossary", "convention", "preference", "routing"];

export default function SemanticMemoryPage() {
    const { projectId } = useParams<{ projectId: string }>();
    const queryClient = useQueryClient();
    const { showToast } = useSnackbar();
    const [q, setQ] = useState("");
    const [vecQ, setVecQ] = useState("");
    const [episodicQ, setEpisodicQ] = useState("");
    const [episodicVecQ, setEpisodicVecQ] = useState("");
    const debouncedQ = useDebounce(q.trim(), 250);
    const debouncedVecQ = useDebounce(vecQ.trim(), 250);
    const debouncedEpisodicQ = useDebounce(episodicQ.trim(), 250);
    const debouncedEpisodicVecQ = useDebounce(episodicVecQ.trim(), 250);
    const [open, setOpen] = useState(false);
    const [form, setForm] = useState({ entry_type: "note", title: "", body: "", ttl_days: "" });
    const [provEntry, setProvEntry] = useState<SemanticMemoryEntry | null>(null);
    const [approvalReason, setApprovalReason] = useState<Record<string, string>>({});

    const projectQuery = useQuery({
        queryKey: queryKeys.orchestration.project(projectId!),
        queryFn: () => getOrchestrationProject(projectId!),
        enabled: !!projectId,
    });
    const project = projectQuery.data;

    const { data: memSettings } = useQuery({
        queryKey: queryKeys.orchestration.memorySettings(projectId!),
        queryFn: () => getProjectMemorySettings(projectId!),
        enabled: !!projectId,
    });

    const settingsMut = useMutation({
        mutationFn: (patch: Parameters<typeof patchProjectMemorySettings>[1]) =>
            patchProjectMemorySettings(projectId!, patch),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.memorySettings(projectId!) });
        },
    });

    const entriesQuery = useQuery({
        queryKey: queryKeys.orchestration.semantic(projectId!, debouncedQ, debouncedVecQ),
        queryFn: () =>
            listSemanticMemory(projectId!, {
                q: debouncedQ || undefined,
                vec_q: debouncedVecQ || undefined,
                limit: 100,
            }),
        enabled: !!projectId,
    });
    const entries = useMemo(() => entriesQuery.data ?? [], [entriesQuery.data]);
    const isLoading = entriesQuery.isLoading;

    const { data: episodic } = useQuery({
        queryKey: queryKeys.orchestration.episodic(projectId!, debouncedEpisodicQ, debouncedEpisodicVecQ),
        queryFn: () =>
            searchEpisodicMemory(projectId!, {
                q: debouncedEpisodicQ || undefined,
                vec_q: debouncedEpisodicVecQ || undefined,
                limit: 40,
            }),
        enabled: !!projectId,
    });

    const { data: conflictGroups = [] } = useQuery({
        queryKey: queryKeys.orchestration.semanticConflicts(projectId!),
        queryFn: () => listSemanticMemoryConflicts(projectId!),
        enabled: !!projectId,
    });

    const { data: episodicArchives = [] } = useQuery({
        queryKey: queryKeys.orchestration.episodicArchives(projectId!),
        queryFn: () => listEpisodicArchives(projectId!),
        enabled: !!projectId,
    });

    const { data: runs = [] } = useQuery({
        queryKey: queryKeys.orchestration.runsMemoryPage(projectId!),
        queryFn: () => listRuns(projectId!),
        enabled: !!projectId,
    });
    const latestRunId = runs[0]?.id;
    const { data: latestWm } = useQuery({
        queryKey: queryKeys.orchestration.runWorkingMemory(latestRunId!),
        queryFn: () => getRunWorkingMemory(latestRunId!),
        enabled: Boolean(latestRunId),
    });

    const { data: playbooks = [] } = useQuery({
        queryKey: queryKeys.orchestration.procedural(projectId!),
        queryFn: () => listProceduralPlaybooks(projectId!),
        enabled: !!projectId,
    });

    const { data: allApprovals = [] } = useQuery({
        queryKey: queryKeys.orchestration.approvals,
        queryFn: () => listApprovals(),
    });
    const semanticApprovals = useMemo(
        () =>
            (allApprovals as Approval[]).filter(
                (a) => a.status === "pending" && a.project_id === projectId && a.approval_type === "semantic_memory_write",
            ),
        [allApprovals, projectId],
    );

    const namespaceTree = useMemo(() => {
        const roots: Record<string, Record<string, Set<string>>> = {};
        for (const e of entries) {
            const parts = (e.namespace || "").split("/").filter(Boolean);
            const company = parts[0] ?? "(root)";
            const proj = parts[1] ?? "·";
            const rest = parts.slice(2).join("/") || "·";
            roots[company] ??= {};
            roots[company][proj] ??= new Set();
            roots[company][proj].add(rest);
        }
        return roots;
    }, [entries]);

    const mergeMut = useMutation({
        mutationFn: (args: { canonical_entry_id: string; merge_entry_ids: string[] }) =>
            mergeSemanticMemoryEntries(projectId!, args),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.semanticRoot(projectId!) });
            await queryClient.invalidateQueries({
                queryKey: queryKeys.orchestration.semanticConflicts(projectId!),
            });
            showToast({ message: "Merged entries into the canonical row.", severity: "success" });
        },
    });

    const reindexMut = useMutation({
        mutationFn: () => reindexEpisodicMemory(projectId!, 300),
        onSuccess: async (res) => {
            await queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.episodicRoot(projectId!) });
            showToast({ message: `Indexed ${res.indexed} episodic rows for search.`, severity: "success" });
        },
    });

    const decideMut = useMutation({
        mutationFn: (args: { approvalId: string; status: "approved" | "rejected"; reason?: string }) =>
            decideApproval(args.approvalId, { status: args.status, reason: args.reason }),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.approvals });
            await queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.semanticRoot(projectId!) });
            showToast({ message: "Approval updated.", severity: "success" });
        },
    });

    const createMut = useMutation({
        mutationFn: () =>
            createSemanticMemory(projectId!, {
                entry_type: form.entry_type,
                title: form.title.trim(),
                body: form.body.trim(),
                ttl_days: form.ttl_days.trim() ? Number(form.ttl_days) : undefined,
            }),
        onSuccess: async (res) => {
            if (isPendingSemanticWrite(res)) {
                showToast({
                    message: "Write submitted for approval. It will appear after approval in the approvals queue.",
                    severity: "info",
                });
                setOpen(false);
                setForm({ entry_type: "note", title: "", body: "", ttl_days: "" });
                return;
            }
            await queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.semanticRoot(projectId!) });
            await queryClient.invalidateQueries({
                queryKey: queryKeys.orchestration.semanticConflicts(projectId!),
            });
            setOpen(false);
            setForm({ entry_type: "note", title: "", body: "", ttl_days: "" });
        },
    });

    if (!projectId) return null;

    const memoryLoadFailed = projectQuery.isError || entriesQuery.isError;
    const memoryRetrying = projectQuery.isFetching || entriesQuery.isFetching;
    const memoryErrorMessage = extractApiErrorMessage(
        projectQuery.error ?? entriesQuery.error,
        "Couldn't load project memory. Check your connection and try again.",
    );

    if (projectQuery.isLoading) {
        return (
            <PageShell maxWidth="lg">
                <Typography color="text.secondary">Loading memory…</Typography>
            </PageShell>
        );
    }

    if (projectQuery.isError && !project) {
        return (
            <PageShell maxWidth="lg">
                <EmptyState
                    icon={<ErrorOutlineIcon />}
                    title="Couldn't load project memory"
                    description={memoryErrorMessage}
                    action={
                        <Button
                            variant="contained"
                            startIcon={<RefreshIcon />}
                            disabled={memoryRetrying}
                            onClick={() => {
                                void projectQuery.refetch();
                                void entriesQuery.refetch();
                            }}
                        >
                            {memoryRetrying ? "Retrying…" : "Try again"}
                        </Button>
                    }
                />
            </PageShell>
        );
    }

    return (
        <PageShell maxWidth="lg">

            {memoryLoadFailed && project && (
                <Alert
                    severity="error"
                    sx={{ mb: 2 }}
                    action={
                        <Button
                            color="inherit"
                            size="small"
                            disabled={memoryRetrying}
                            onClick={() => {
                                void projectQuery.refetch();
                                void entriesQuery.refetch();
                            }}
                        >
                            {memoryRetrying ? "Retrying…" : "Retry"}
                        </Button>
                    }
                >
                    {memoryErrorMessage}
                </Alert>
            )}

            <CollapsibleSectionCard
                title="Memory stack (5 layers)"
                description="Where each layer lives in this product; drill down in sections below."
                defaultExpanded
                sx={{ mb: 3 }}
            >
                <Stack spacing={1.5}>
                    <Paper variant="outlined" sx={{ p: 1.5, borderRadius: 1 }}>
                        <Typography variant="subtitle2">1 · Working memory</Typography>
                        <Typography variant="body2" color="text.secondary">
                            Latest run scratchpad (objective, plan, findings). Shown live on Run Inspector; sample from most
                            recent project run below.
                        </Typography>
                        {latestWm ? (
                            <Typography variant="caption" component="pre" sx={{ display: "block", mt: 1, whiteSpace: "pre-wrap" }}>
                                {JSON.stringify(
                                    {
                                        objective: latestWm.objective?.slice(0, 200),
                                        latest_findings: latestWm.latest_findings?.slice(0, 200),
                                        updated_at: latestWm.updated_at,
                                    },
                                    null,
                                    2,
                                )}
                            </Typography>
                        ) : (
                            <Typography variant="caption" color="text.secondary">
                                No run working memory loaded.
                            </Typography>
                        )}
                        {latestRunId ? (
                            <Button component={RouterLink} to={`/runs/${latestRunId}`} size="small" sx={{ mt: 1 }}>
                                Open latest run
                            </Button>
                        ) : null}
                    </Paper>
                    <Paper variant="outlined" sx={{ p: 1.5, borderRadius: 1 }}>
                        <Typography variant="subtitle2">2 · Semantic (this page)</Typography>
                        <Typography variant="body2" color="text.secondary">
                            Typed entries with provenance + confidence. Vector + keyword search above.
                        </Typography>
                    </Paper>
                    <Paper variant="outlined" sx={{ p: 1.5, borderRadius: 1 }}>
                        <Typography variant="subtitle2">3 · Episodic</Typography>
                        <Typography variant="body2" color="text.secondary">
                            Search + cold archives below; execution-derived snippets from runs, comments, brainstorms.
                        </Typography>
                    </Paper>
                    <Paper variant="outlined" sx={{ p: 1.5, borderRadius: 1 }}>
                        <Typography variant="subtitle2">4 · Procedural</Typography>
                        <Typography variant="body2" color="text.secondary">
                            Playbooks ({playbooks.length}) — markdown SOPs injected into context when namespaces match.
                        </Typography>
                        <Stack spacing={0.5} sx={{ mt: 1, maxHeight: 120, overflow: "auto" }}>
                            {playbooks.length === 0 ? (
                                <Typography variant="caption" color="text.secondary">
                                    No playbooks yet.
                                </Typography>
                            ) : (
                                playbooks.map((pb) => (
                                    <Typography key={pb.id} variant="caption" sx={{ display: "block" }}>
                                        {pb.title} · <code>{pb.namespace}</code>
                                    </Typography>
                                ))
                            )}
                        </Stack>
                    </Paper>
                    <Paper variant="outlined" sx={{ p: 1.5, borderRadius: 1 }}>
                        <Typography variant="subtitle2">5 · Execution events</Typography>
                        <Typography variant="body2" color="text.secondary">
                            Durable run_event log + task timeline on the project board. Recent runs:{" "}
                            {runs.slice(0, 5).map((r) => (
                                <Link key={r.id} component={RouterLink} to={`/runs/${r.id}`} sx={{ mr: 1 }}>
                                    {r.id.slice(0, 6)}…
                                </Link>
                            ))}
                        </Typography>
                    </Paper>
                </Stack>
            </CollapsibleSectionCard>

            <CollapsibleSectionCard
                title="Namespace map (from visible semantic rows)"
                description="company / project prefix / remainder — derived from entry.namespace strings."
                sx={{ mb: 3 }}
            >
                {Object.keys(namespaceTree).length === 0 ? (
                    <Typography color="text.secondary">No namespaces in current result set.</Typography>
                ) : (
                    <Stack spacing={1}>
                        {Object.entries(namespaceTree).map(([c, projs]) => (
                            <Box key={c}>
                                <Typography variant="subtitle2">{c}</Typography>
                                {Object.entries(projs).map(([p, rests]) => (
                                    <Box key={`${c}/${p}`} sx={{ pl: 2, mt: 0.5 }}>
                                        <Typography variant="caption" color="text.secondary">
                                            {p}
                                        </Typography>
                                        <Stack sx={{ pl: 2 }}>
                                            {[...rests].slice(0, 12).map((r) => (
                                                <Typography key={r} variant="caption" sx={{ display: "block" }}>
                                                    {r}
                                                </Typography>
                                            ))}
                                        </Stack>
                                    </Box>
                                ))}
                            </Box>
                        ))}
                    </Stack>
                )}
            </CollapsibleSectionCard>

            <SectionCard
                title="Semantic write approvals"
                description="Queue when “Require approval for manual semantic writes” is on (and bypass is off)."
                sx={{ mb: 3 }}
            >
                {semanticApprovals.length === 0 ? (
                    <Typography color="text.secondary">No pending semantic approvals for this project.</Typography>
                ) : (
                    <Stack spacing={1.5}>
                        {semanticApprovals.map((a) => (
                            <Paper key={a.id} variant="outlined" sx={{ p: 1.5, borderRadius: 1 }}>
                                <Stack spacing={1}>
                                    <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                                        <Chip size="small" label={a.approval_type} />
                                        <Typography variant="caption" color="text.secondary">
                                            {formatDateTime(a.created_at)}
                                        </Typography>
                                    </Stack>
                                    <Typography variant="caption" component="pre" sx={{ whiteSpace: "pre-wrap", wordBreak: "break-word", m: 0 }}>
                                        {JSON.stringify(a.payload ?? {}, null, 2).slice(0, 1200)}
                                    </Typography>
                                    <TextField
                                        size="small"
                                        label="Reason (required to reject)"
                                        value={approvalReason[a.id] ?? ""}
                                        onChange={(e) => setApprovalReason((m) => ({ ...m, [a.id]: e.target.value }))}
                                    />
                                    <Stack direction="row" spacing={1}>
                                        <Button
                                            size="small"
                                            variant="contained"
                                            disabled={decideMut.isPending}
                                            onClick={() => decideMut.mutate({ approvalId: a.id, status: "approved" })}
                                        >
                                            Approve
                                        </Button>
                                        <Button
                                            size="small"
                                            color="error"
                                            variant="outlined"
                                            disabled={decideMut.isPending}
                                            onClick={() => {
                                                const reason = (approvalReason[a.id] ?? "").trim();
                                                if (!reason) {
                                                    showToast({ message: "Rejection needs a reason.", severity: "warning" });
                                                    return;
                                                }
                                                decideMut.mutate({ approvalId: a.id, status: "rejected", reason });
                                            }}
                                        >
                                            Reject
                                        </Button>
                                    </Stack>
                                </Stack>
                            </Paper>
                        ))}
                    </Stack>
                )}
            </SectionCard>

            <SectionCard
                title="Memory automation"
                description="Controls auto-ingest from decisions and approved agent memory, episodic second stage, retention, deep recall, and task-close promotion."
                sx={{ mb: 3 }}
            >
                {memSettings ? (
                    <Stack spacing={1}>
                        <FormControlLabel
                            control={
                                <Switch
                                    checked={memSettings.auto_promote_decisions}
                                    onChange={(_, v) =>
                                        settingsMut.mutate({ auto_promote_decisions: v })
                                    }
                                    disabled={settingsMut.isPending}
                                />
                            }
                            label="Auto-promote project decisions to semantic memory"
                        />
                        <FormControlLabel
                            control={
                                <Switch
                                    checked={memSettings.auto_promote_approved_agent_memory}
                                    onChange={(_, v) =>
                                        settingsMut.mutate({ auto_promote_approved_agent_memory: v })
                                    }
                                    disabled={settingsMut.isPending}
                                />
                            }
                            label="Auto-promote approved agent memory writes"
                        />
                        <FormControlLabel
                            control={
                                <Switch
                                    checked={memSettings.second_stage_rag}
                                    onChange={(_, v) => settingsMut.mutate({ second_stage_rag: v })}
                                    disabled={settingsMut.isPending}
                                />
                            }
                            label="Second-stage episodic recall in agent context packets"
                        />
                        <FormControlLabel
                            control={
                                <Switch
                                    checked={memSettings.task_close_auto_promote_working_memory}
                                    onChange={(_, v) =>
                                        settingsMut.mutate({ task_close_auto_promote_working_memory: v })
                                    }
                                    disabled={settingsMut.isPending}
                                />
                            }
                            label="On task close, promote working memory to semantic (snapshot)"
                        />
                        <FormControlLabel
                            control={
                                <Switch
                                    checked={memSettings.enable_semantic_vector_search}
                                    onChange={(_, v) =>
                                        settingsMut.mutate({ enable_semantic_vector_search: v })
                                    }
                                    disabled={settingsMut.isPending}
                                />
                            }
                            label="Enable pgvector merge when using vector query below"
                        />
                        <FormControlLabel
                            control={
                                <Switch
                                    checked={memSettings.semantic_write_requires_approval}
                                    onChange={(_, v) =>
                                        settingsMut.mutate({ semantic_write_requires_approval: v })
                                    }
                                    disabled={settingsMut.isPending}
                                />
                            }
                            label="Require approval for manual semantic writes (create / update / delete)"
                        />
                        <FormControlLabel
                            control={
                                <Switch
                                    checked={memSettings.auto_ingest_bypasses_semantic_approval}
                                    onChange={(_, v) =>
                                        settingsMut.mutate({ auto_ingest_bypasses_semantic_approval: v })
                                    }
                                    disabled={settingsMut.isPending}
                                />
                            }
                            label="Auto-ingest and promotions bypass the semantic approval gate"
                        />
                        <FormControlLabel
                            control={
                                <Switch
                                    checked={memSettings.episodic_archive_enabled}
                                    onChange={(_, v) => settingsMut.mutate({ episodic_archive_enabled: v })}
                                    disabled={settingsMut.isPending}
                                />
                            }
                            label="Archive episodic snapshots to cold storage on retention sweep"
                        />
                        <FormControlLabel
                            control={
                                <Switch
                                    checked={memSettings.episodic_delete_index_after_archive}
                                    onChange={(_, v) =>
                                        settingsMut.mutate({ episodic_delete_index_after_archive: v })
                                    }
                                    disabled={settingsMut.isPending}
                                />
                            }
                            label="After archive, drop old episodic search-index rows (run history stays in DB)"
                        />
                        <FormControlLabel
                            control={
                                <Switch
                                    checked={memSettings.enable_episodic_vector_search}
                                    onChange={(_, v) =>
                                        settingsMut.mutate({ enable_episodic_vector_search: v })
                                    }
                                    disabled={settingsMut.isPending}
                                />
                            }
                            label="Approximate episodic vector pass (combine with keyword episodic query)"
                        />
                        <FormControlLabel
                            control={
                                <Switch
                                    checked={memSettings.deep_recall_mode}
                                    onChange={(_, v) => settingsMut.mutate({ deep_recall_mode: v })}
                                    disabled={settingsMut.isPending}
                                />
                            }
                            label="Deep recall: episodic index + second-stage semantic approximate in agent context"
                        />
                        <FormControlLabel
                            control={
                                <Switch
                                    checked={memSettings.classifier_worker_enabled}
                                    onChange={(_, v) =>
                                        settingsMut.mutate({ classifier_worker_enabled: v })
                                    }
                                    disabled={settingsMut.isPending}
                                />
                            }
                            label="Unified classifier worker (memory ingest jobs for embeddings)"
                        />
                        <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
                            <TextField
                                key={`ret-${memSettings.episodic_retention_days}`}
                                label="Episodic retention (days)"
                                type="number"
                                size="small"
                                defaultValue={String(memSettings.episodic_retention_days)}
                                onBlur={(e) => {
                                    const n = Number(e.target.value);
                                    if (!Number.isFinite(n)) return;
                                    settingsMut.mutate({ episodic_retention_days: Math.round(n) });
                                }}
                                disabled={settingsMut.isPending}
                                inputProps={{ min: 1, max: 3650 }}
                                fullWidth
                            />
                            <TextField
                                key={`deep-${memSettings.deep_recall_episodic_candidates}`}
                                label="Deep recall episodic candidates"
                                type="number"
                                size="small"
                                defaultValue={String(memSettings.deep_recall_episodic_candidates)}
                                onBlur={(e) => {
                                    const n = Number(e.target.value);
                                    if (!Number.isFinite(n)) return;
                                    settingsMut.mutate({
                                        deep_recall_episodic_candidates: Math.round(n),
                                    });
                                }}
                                disabled={settingsMut.isPending}
                                inputProps={{ min: 4, max: 200 }}
                                fullWidth
                            />
                            <TextField
                                key={`depth-${memSettings.episodic_retrieval_depth}`}
                                label="Episodic retrieval depth"
                                type="number"
                                size="small"
                                defaultValue={String(memSettings.episodic_retrieval_depth)}
                                onBlur={(e) => {
                                    const n = Number(e.target.value);
                                    if (!Number.isFinite(n)) return;
                                    settingsMut.mutate({ episodic_retrieval_depth: Math.round(n) });
                                }}
                                disabled={settingsMut.isPending}
                                inputProps={{ min: 1, max: 200 }}
                                fullWidth
                            />
                            <TextField
                                key={`memory-ttl-${memSettings.default_ttl_days}`}
                                label="Default semantic TTL (days)"
                                type="number"
                                size="small"
                                defaultValue={String(memSettings.default_ttl_days)}
                                onBlur={(e) => {
                                    const n = Number(e.target.value);
                                    if (!Number.isFinite(n)) return;
                                    settingsMut.mutate({ default_ttl_days: Math.round(n) });
                                }}
                                helperText="0 keeps entries until explicitly deleted."
                                inputProps={{ min: 0, max: memSettings.max_ttl_days }}
                                disabled={settingsMut.isPending}
                                fullWidth
                            />
                            <TextField
                                key={`memory-context-${memSettings.context_max_tokens}`}
                                label="Memory context budget (tokens)"
                                type="number"
                                size="small"
                                defaultValue={String(memSettings.context_max_tokens)}
                                onBlur={(e) => {
                                    const n = Number(e.target.value);
                                    if (!Number.isFinite(n)) return;
                                    settingsMut.mutate({ context_max_tokens: Math.round(n) });
                                }}
                                inputProps={{ min: 64, max: 12000 }}
                                disabled={settingsMut.isPending}
                                fullWidth
                            />
                        </Stack>
                    </Stack>
                ) : (
                    <Typography color="text.secondary">Loading settings…</Typography>
                )}
            </SectionCard>

            <SectionCard
                title="Semantic memory"
                description={project ? project.name : undefined}
                action={
                    <Button variant="contained" onClick={() => setOpen(true)}>
                        New entry
                    </Button>
                }
            >
                <Stack direction={{ xs: "column", sm: "row" }} spacing={2} sx={{ mb: 2 }}>
                    <TextField
                        label="Search title/body"
                        value={q}
                        onChange={(e) => setQ(e.target.value)}
                        size="small"
                        fullWidth
                    />
                    <TextField
                        label="Vector query (optional)"
                        value={vecQ}
                        onChange={(e) => setVecQ(e.target.value)}
                        size="small"
                        fullWidth
                        helperText="Uses embeddings when enabled in settings"
                    />
                </Stack>
                {isLoading ? (
                    <Typography color="text.secondary">Loading…</Typography>
                ) : entries.length === 0 ? (
                    <Typography color="text.secondary">No entries yet.</Typography>
                ) : (
                    <TableContainer sx={{ width: "100%", overflowX: "auto" }}>
                    <Table size="small">
                        <TableHead>
                            <TableRow>
                                <TableCell>Type</TableCell>
                                <TableCell>Title</TableCell>
                                <TableCell>Namespace</TableCell>
                                <TableCell>Source</TableCell>
                                <TableCell>Prov.</TableCell>
                                <TableCell>Confidence</TableCell>
                                <TableCell>Updated</TableCell>
                                <TableCell>Retention</TableCell>
                            </TableRow>
                        </TableHead>
                        <TableBody>
                            {entries.map((row: SemanticMemoryEntry) => {
                                const source = String(
                                    (row.provenance as Record<string, unknown>)?.source ?? "api",
                                );
                                const conf = typeof row.confidence === "number" ? row.confidence : 0.5;
                                const confColor =
                                    conf >= 0.75 ? "success.main" : conf >= 0.5 ? "warning.main" : "error.main";
                                const expiryLabel = row.expires_at
                                    ? `Expires ${formatDateTime(row.expires_at)}`
                                    : "No expiry";
                                return (
                                    <TableRow key={row.id}>
                                        <TableCell>{row.entry_type}</TableCell>
                                        <TableCell>
                                            <Typography variant="body2" fontWeight={600}>
                                                {row.title}
                                            </Typography>
                                            <Typography
                                                variant="caption"
                                                color="text.secondary"
                                                sx={{ display: "block" }}
                                            >
                                                {(row.body || "").slice(0, 160)}
                                                {(row.body || "").length > 160 ? "…" : ""}
                                            </Typography>
                                        </TableCell>
                                        <TableCell>
                                            <Typography variant="caption" sx={{ wordBreak: "break-all" }}>
                                                {row.namespace}
                                            </Typography>
                                        </TableCell>
                                        <TableCell>
                                            <Typography variant="caption" color="text.secondary">
                                                {source}
                                            </Typography>
                                        </TableCell>
                                        <TableCell>
                                            <Tooltip title="View full provenance JSON">
                                                <IconButton size="small" onClick={() => setProvEntry(row)} aria-label="provenance">
                                                    <InfoOutlinedIcon fontSize="small" />
                                                </IconButton>
                                            </Tooltip>
                                        </TableCell>
                                        <TableCell>
                                            <Typography variant="caption" sx={{ color: confColor, fontWeight: 500 }}>
                                                {(conf * 100).toFixed(0)}%
                                            </Typography>
                                        </TableCell>
                                        <TableCell>{formatDateTime(row.updated_at)}</TableCell>
                                        <TableCell>
                                            <Typography variant="caption" color="text.secondary">
                                                {expiryLabel}
                                            </Typography>
                                        </TableCell>
                                    </TableRow>
                                );
                            })}
                        </TableBody>
                    </Table>
                    </TableContainer>
                )}
            </SectionCard>

            <SectionCard
                title="Conflict resolver"
                description="Duplicate-title groups plus embedding-based near-duplicates and contradictions detected across existing entries."
                sx={{ mt: 3 }}
                action={
                    <Button
                        size="small"
                        variant="outlined"
                        onClick={() =>
                            queryClient.invalidateQueries({
                                queryKey: queryKeys.orchestration.semanticConflicts(projectId!),
                            })
                        }
                    >
                        Refresh
                    </Button>
                }
            >
                {conflictGroups.length === 0 ? (
                    <Typography color="text.secondary">No duplicate-title groups detected.</Typography>
                ) : (
                    <Stack spacing={2}>
                        {conflictGroups.map((g) => (
                            <Box key={g.group_key}>
                                <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}>
                                    <Typography variant="subtitle2">{g.group_key}</Typography>
                                    {g.kind && g.kind !== "title_duplicate" && (
                                        <Typography
                                            variant="caption"
                                            sx={{
                                                px: 0.75,
                                                py: 0.25,
                                                borderRadius: 1,
                                                bgcolor:
                                                    g.kind === "contradicts"
                                                        ? "error.light"
                                                        : "warning.light",
                                                color: "#000",
                                            }}
                                        >
                                            {g.kind}
                                            {typeof g.similarity === "number"
                                                ? ` · sim ${(g.similarity * 100).toFixed(0)}%`
                                                : ""}
                                        </Typography>
                                    )}
                                </Stack>
                                {g.reason && (
                                    <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1 }}>
                                        {g.reason}
                                    </Typography>
                                )}
                                <TableContainer sx={{ width: "100%", overflowX: "auto" }}>
                                <Table size="small">
                                    <TableHead>
                                        <TableRow>
                                            <TableCell>Title</TableCell>
                                            <TableCell>Namespace</TableCell>
                                            <TableCell align="right">Updated</TableCell>
                                        </TableRow>
                                    </TableHead>
                                    <TableBody>
                                        {g.entries.map((e) => (
                                            <TableRow key={e.id}>
                                                <TableCell>{e.title}</TableCell>
                                                <TableCell>
                                                    <Typography variant="caption" sx={{ wordBreak: "break-all" }}>
                                                        {e.namespace}
                                                    </Typography>
                                                </TableCell>
                                                <TableCell align="right">
                                                    <Typography variant="caption" color="text.secondary">
                                                        {formatDateTime(e.updated_at)}
                                                    </Typography>
                                                </TableCell>
                                            </TableRow>
                                        ))}
                                    </TableBody>
                                </Table>
                                </TableContainer>
                                <Button
                                    size="small"
                                    variant="contained"
                                    sx={{ mt: 1 }}
                                    disabled={g.entries.length < 2 || mergeMut.isPending}
                                    onClick={() => {
                                        const [first, ...rest] = g.entries;
                                        mergeMut.mutate({
                                            canonical_entry_id: first.id,
                                            merge_entry_ids: rest.map((x) => x.id),
                                        });
                                    }}
                                >
                                    Merge into first row
                                </Button>
                            </Box>
                        ))}
                    </Stack>
                )}
            </SectionCard>

            <SectionCard
                title="Episodic search"
                sx={{ mt: 3 }}
                action={
                    <Button
                        size="small"
                        variant="outlined"
                        disabled={reindexMut.isPending}
                        onClick={() => reindexMut.mutate()}
                    >
                        Reindex recent runs
                    </Button>
                }
            >
                <Stack direction={{ xs: "column", sm: "row" }} spacing={2} sx={{ mb: 2 }}>
                    <TextField
                        label="Keyword (optional)"
                        value={episodicQ}
                        onChange={(e) => setEpisodicQ(e.target.value)}
                        size="small"
                        fullWidth
                    />
                    <TextField
                        label="Vector query (optional)"
                        value={episodicVecQ}
                        onChange={(e) => setEpisodicVecQ(e.target.value)}
                        size="small"
                        fullWidth
                        helperText="Second-stage approximate when episodic vector search is enabled"
                    />
                </Stack>
                <Stack spacing={1}>
                    {(episodic?.hits ?? []).slice(0, 25).map((hit, i) => (
                        <Box key={`${hit.kind}-${hit.id}-${i}`} sx={{ py: 0.5 }}>
                            <Typography variant="caption" color="text.secondary">
                                {String(hit.kind)} · {formatDateTime(String(hit.created_at))}
                            </Typography>
                            <Typography variant="body2">{String(hit.snippet ?? "").slice(0, 400)}</Typography>
                        </Box>
                    ))}
                    {(episodic?.hits ?? []).length === 0 && (
                        <Typography color="text.secondary">No matches.</Typography>
                    )}
                </Stack>
            </SectionCard>

            <SectionCard title="Cold archives (manifests)" description="JSONL.gz snapshots written by the retention job." sx={{ mt: 3 }}>
                {episodicArchives.length === 0 ? (
                    <Typography color="text.secondary">No archives yet.</Typography>
                ) : (
                    <TableContainer sx={{ width: "100%", overflowX: "auto" }}>
                    <Table size="small">
                        <TableHead>
                            <TableRow>
                                <TableCell>Period</TableCell>
                                <TableCell>Records</TableCell>
                                <TableCell>Size</TableCell>
                                <TableCell>Object key</TableCell>
                            </TableRow>
                        </TableHead>
                        <TableBody>
                            {episodicArchives.map((a) => (
                                <TableRow key={a.id}>
                                    <TableCell>
                                        <Typography variant="caption">
                                            {formatDateTime(a.period_start)} — {formatDateTime(a.period_end)}
                                        </Typography>
                                    </TableCell>
                                    <TableCell>{a.record_count}</TableCell>
                                    <TableCell>{(a.byte_size / 1024).toFixed(1)} KiB</TableCell>
                                    <TableCell>
                                        <Typography variant="caption" sx={{ wordBreak: "break-all" }}>
                                            {a.object_key}
                                        </Typography>
                                    </TableCell>
                                </TableRow>
                            ))}
                        </TableBody>
                    </Table>
                    </TableContainer>
                )}
            </SectionCard>

            <Dialog open={Boolean(provEntry)} onClose={() => setProvEntry(null)} fullWidth maxWidth="md">
                <DialogTitle>Provenance & metadata</DialogTitle>
                <DialogContent>
                    {provEntry ? (
                        <Stack spacing={1} sx={{ mt: 1 }}>
                            <Typography variant="caption" color="text.secondary">
                                Entry {provEntry.id}
                            </Typography>
                            <Typography variant="caption" component="pre" sx={{ whiteSpace: "pre-wrap", wordBreak: "break-word", m: 0 }}>
                                {JSON.stringify(
                                    {
                                        provenance: provEntry.provenance,
                                        metadata: provEntry.metadata,
                                        source_task_id: provEntry.source_task_id,
                                        source_run_id: provEntry.source_run_id,
                                        confidence: provEntry.confidence,
                                    },
                                    null,
                                    2,
                                )}
                            </Typography>
                        </Stack>
                    ) : null}
                </DialogContent>
                <DialogActions>
                    <Button onClick={() => setProvEntry(null)}>Close</Button>
                </DialogActions>
            </Dialog>

            <Dialog open={open} onClose={() => setOpen(false)} fullWidth maxWidth="sm">
                <DialogTitle>New semantic entry</DialogTitle>
                <DialogContent>
                    <Stack spacing={2} sx={{ mt: 1 }}>
                        <TextField
                            select
                            label="Type"
                            value={form.entry_type}
                            onChange={(e) => setForm((f) => ({ ...f, entry_type: e.target.value }))}
                        >
                            {ENTRY_TYPES.map((t) => (
                                <MenuItem key={t} value={t}>
                                    {t}
                                </MenuItem>
                            ))}
                        </TextField>
                        <TextField
                            label="Title"
                            value={form.title}
                            onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
                            required
                        />
                        <TextField
                            label="Body"
                            value={form.body}
                            onChange={(e) => setForm((f) => ({ ...f, body: e.target.value }))}
                            multiline
                            minRows={4}
                            required
                        />
                        <TextField
                            label="TTL (days, optional)"
                            type="number"
                            value={form.ttl_days}
                            onChange={(e) => setForm((f) => ({ ...f, ttl_days: e.target.value }))}
                            helperText="Leave empty to use the project default."
                            inputProps={{ min: 1, max: memSettings?.max_ttl_days ?? 3650 }}
                        />
                    </Stack>
                </DialogContent>
                <DialogActions>
                    <Button onClick={() => setOpen(false)}>Cancel</Button>
                    <Button
                        variant="contained"
                        disabled={!form.title.trim() || !form.body.trim() || createMut.isPending}
                        onClick={() => createMut.mutate()}
                    >
                        Save
                    </Button>
                </DialogActions>
            </Dialog>
        </PageShell>
    );
}
