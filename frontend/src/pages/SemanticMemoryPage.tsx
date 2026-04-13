import { useState } from "react";
import { Link as RouterLink, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
    Alert,
    Box,
    Button,
    Dialog,
    DialogActions,
    DialogContent,
    DialogTitle,
    FormControlLabel,
    Link,
    MenuItem,
    Stack,
    Switch,
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableRow,
    TextField,
    Typography,
} from "@mui/material";
import {
    createSemanticMemory,
    getOrchestrationProject,
    getProjectMemorySettings,
    isPendingSemanticWrite,
    listEpisodicArchives,
    listSemanticMemory,
    listSemanticMemoryConflicts,
    mergeSemanticMemoryEntries,
    patchProjectMemorySettings,
    reindexEpisodicMemory,
    searchEpisodicMemory,
    type SemanticMemoryEntry,
} from "../api/orchestration";
import { PageHeader } from "../components/ui/PageHeader";
import { PageShell } from "../components/ui/PageShell";
import { SectionCard } from "../components/ui/SectionCard";
import { formatDateTime } from "../utils/formatters";

const ENTRY_TYPES = ["note", "policy", "standard", "adr", "glossary", "convention", "preference", "routing"];

export default function SemanticMemoryPage() {
    const { projectId } = useParams<{ projectId: string }>();
    const queryClient = useQueryClient();
    const [q, setQ] = useState("");
    const [vecQ, setVecQ] = useState("");
    const [episodicQ, setEpisodicQ] = useState("");
    const [episodicVecQ, setEpisodicVecQ] = useState("");
    const [open, setOpen] = useState(false);
    const [form, setForm] = useState({ entry_type: "note", title: "", body: "" });
    const [notice, setNotice] = useState<string | null>(null);

    const { data: project } = useQuery({
        queryKey: ["orchestration", "project", projectId],
        queryFn: () => getOrchestrationProject(projectId!),
        enabled: !!projectId,
    });

    const { data: memSettings } = useQuery({
        queryKey: ["orchestration", "memory-settings", projectId],
        queryFn: () => getProjectMemorySettings(projectId!),
        enabled: !!projectId,
    });

    const settingsMut = useMutation({
        mutationFn: (patch: Parameters<typeof patchProjectMemorySettings>[1]) =>
            patchProjectMemorySettings(projectId!, patch),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "memory-settings", projectId] });
        },
    });

    const { data: entries = [], isLoading } = useQuery({
        queryKey: ["orchestration", "semantic", projectId, q, vecQ],
        queryFn: () =>
            listSemanticMemory(projectId!, {
                q: q.trim() || undefined,
                vec_q: vecQ.trim() || undefined,
                limit: 100,
            }),
        enabled: !!projectId,
    });

    const { data: episodic } = useQuery({
        queryKey: ["orchestration", "episodic", projectId, episodicQ, episodicVecQ],
        queryFn: () =>
            searchEpisodicMemory(projectId!, {
                q: episodicQ.trim() || undefined,
                vec_q: episodicVecQ.trim() || undefined,
                limit: 40,
            }),
        enabled: !!projectId,
    });

    const { data: conflictGroups = [] } = useQuery({
        queryKey: ["orchestration", "semantic-conflicts", projectId],
        queryFn: () => listSemanticMemoryConflicts(projectId!),
        enabled: !!projectId,
    });

    const { data: episodicArchives = [] } = useQuery({
        queryKey: ["orchestration", "episodic-archives", projectId],
        queryFn: () => listEpisodicArchives(projectId!),
        enabled: !!projectId,
    });

    const mergeMut = useMutation({
        mutationFn: (args: { canonical_entry_id: string; merge_entry_ids: string[] }) =>
            mergeSemanticMemoryEntries(projectId!, args),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "semantic", projectId] });
            await queryClient.invalidateQueries({
                queryKey: ["orchestration", "semantic-conflicts", projectId],
            });
            setNotice("Merged entries into the canonical row.");
        },
    });

    const reindexMut = useMutation({
        mutationFn: () => reindexEpisodicMemory(projectId!, 300),
        onSuccess: async (res) => {
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "episodic", projectId] });
            setNotice(`Indexed ${res.indexed} episodic rows for search.`);
        },
    });

    const createMut = useMutation({
        mutationFn: () =>
            createSemanticMemory(projectId!, {
                entry_type: form.entry_type,
                title: form.title.trim(),
                body: form.body.trim(),
            }),
        onSuccess: async (res) => {
            if (isPendingSemanticWrite(res)) {
                setNotice(
                    "Write submitted for approval. It will appear after approval in the approvals queue."
                );
                setOpen(false);
                setForm({ entry_type: "note", title: "", body: "" });
                return;
            }
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "semantic", projectId] });
            await queryClient.invalidateQueries({
                queryKey: ["orchestration", "semantic-conflicts", projectId],
            });
            setOpen(false);
            setForm({ entry_type: "note", title: "", body: "" });
        },
    });

    if (!projectId) return null;

    return (
        <PageShell maxWidth="lg">
            <PageHeader
                eyebrow="Memory"
                title="Semantic & episodic"
                description={
                    <>
                        Typed semantic entries for this project. Episodic search scans run events, comments,
                        and brainstorm messages.{" "}
                        <Link component={RouterLink} to={`/agent-projects/${projectId}`}>
                            Back to project
                        </Link>
                    </>
                }
            />

            {notice && (
                <Alert severity="info" onClose={() => setNotice(null)} sx={{ mb: 2 }}>
                    {notice}
                </Alert>
            )}

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
                    <Table size="small">
                        <TableHead>
                            <TableRow>
                                <TableCell>Type</TableCell>
                                <TableCell>Title</TableCell>
                                <TableCell>Namespace</TableCell>
                                <TableCell>Updated</TableCell>
                            </TableRow>
                        </TableHead>
                        <TableBody>
                            {entries.map((row: SemanticMemoryEntry) => (
                                <TableRow key={row.id}>
                                    <TableCell>{row.entry_type}</TableCell>
                                    <TableCell>
                                        <Typography variant="body2" fontWeight={600}>
                                            {row.title}
                                        </Typography>
                                        <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
                                            {(row.body || "").slice(0, 160)}
                                            {(row.body || "").length > 160 ? "…" : ""}
                                        </Typography>
                                    </TableCell>
                                    <TableCell>
                                        <Typography variant="caption" sx={{ wordBreak: "break-all" }}>
                                            {row.namespace}
                                        </Typography>
                                    </TableCell>
                                    <TableCell>{formatDateTime(row.updated_at)}</TableCell>
                                </TableRow>
                            ))}
                        </TableBody>
                    </Table>
                )}
            </SectionCard>

            <SectionCard
                title="Duplicate compaction"
                description="Same title and type but different bodies — merge into one canonical entry (provenance preserved server-side)."
                sx={{ mt: 3 }}
                action={
                    <Button
                        size="small"
                        variant="outlined"
                        onClick={() =>
                            queryClient.invalidateQueries({
                                queryKey: ["orchestration", "semantic-conflicts", projectId],
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
                                <Typography variant="subtitle2" sx={{ mb: 1 }}>
                                    {g.group_key}
                                </Typography>
                                <Table size="small">
                                    <TableHead>
                                        <TableRow>
                                            <TableCell>Title</TableCell>
                                            <TableCell>Namespace</TableCell>
                                            <TableCell align="right">Action</TableCell>
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
                )}
            </SectionCard>

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
