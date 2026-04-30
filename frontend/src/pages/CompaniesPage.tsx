import { useEffect, useMemo, useState } from "react";
import { Link as RouterLink } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
    Alert,
    Box,
    Button,
    Chip,
    Divider,
    MenuItem,
    Paper,
    Stack,
    TextField,
    Typography,
} from "@mui/material";
import {
    createCompany,
    listCompanies,
    updateCompany,
    type Company,
} from "../api/companies";
import { useSnackbar } from "../app/snackbarContext";
import { EmptyState } from "../components/ui/EmptyState";
import { PageShell } from "../components/ui/PageShell";
import { SectionCard } from "../components/ui/SectionCard";
import { formatDateTime } from "../utils/formatters";

const BRIEF_MAX_CHARS = 500;

function slugify(value: string): string {
    return value
        .toLowerCase()
        .replace(/[^a-z0-9-]+/g, "-")
        .replace(/^-+|-+$/g, "")
        .slice(0, 255);
}

export default function CompaniesPage() {
    const queryClient = useQueryClient();
    const { showToast } = useSnackbar();
    const [selectedId, setSelectedId] = useState<string | null>(null);
    const [newName, setNewName] = useState("");
    const [newSlug, setNewSlug] = useState("");
    const [brief, setBrief] = useState("");
    const [editedName, setEditedName] = useState("");

    const { data: companies = [], isLoading } = useQuery({
        queryKey: ["companies"],
        queryFn: listCompanies,
    });

    useEffect(() => {
        if (!selectedId && companies.length) {
            setSelectedId(companies[0].id);
        }
    }, [companies, selectedId]);

    const selected: Company | undefined = useMemo(
        () => companies.find((c) => c.id === selectedId),
        [companies, selectedId],
    );

    useEffect(() => {
        if (selected) {
            setBrief(selected.brief_markdown ?? "");
            setEditedName(selected.name);
        }
    }, [selected?.id]);

    const createMut = useMutation({
        mutationFn: () =>
            createCompany({
                name: newName.trim(),
                slug: slugify(newSlug || newName),
                brief_markdown: "",
            }),
        onSuccess: async (company) => {
            await queryClient.invalidateQueries({ queryKey: ["companies"] });
            setNewName("");
            setNewSlug("");
            setSelectedId(company.id);
            showToast({ message: "Company created.", severity: "success" });
        },
        onError: (err) => {
            showToast({
                message: err instanceof Error ? err.message : "Couldn't create company.",
                severity: "error",
            });
        },
    });

    const updateMut = useMutation({
        mutationFn: () => {
            if (!selected) throw new Error("No company selected");
            return updateCompany(selected.id, {
                name: editedName.trim() || selected.name,
                brief_markdown: brief.slice(0, BRIEF_MAX_CHARS),
            });
        },
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["companies"] });
            showToast({ message: "Company updated.", severity: "success" });
        },
        onError: (err) => {
            showToast({
                message: err instanceof Error ? err.message : "Couldn't update company.",
                severity: "error",
            });
        },
    });

    return (
        <PageShell maxWidth="xl">

            <Box
                sx={{
                    display: "grid",
                    gap: 2,
                    gridTemplateColumns: { xs: "1fr", md: "340px minmax(0, 1fr)" },
                    alignItems: "start",
                }}
            >
                <Stack spacing={2}>
                    <SectionCard
                        title="Create company"
                        description="Each company has its own semantic/procedural memory namespace."
                    >
                        <Stack spacing={1.75}>
                            <TextField
                                label="Name"
                                value={newName}
                                onChange={(e) => setNewName(e.target.value)}
                                inputProps={{ maxLength: 255 }}
                            />
                            <TextField
                                label="Slug"
                                value={newSlug}
                                onChange={(e) => setNewSlug(e.target.value)}
                                helperText="Lowercase, dashes only. Auto-generated from name if blank."
                                inputProps={{ maxLength: 255 }}
                            />
                            <Button
                                variant="contained"
                                disabled={!newName.trim() || createMut.isPending}
                                onClick={() => createMut.mutate()}
                            >
                                Create
                            </Button>
                        </Stack>
                    </SectionCard>

                    <SectionCard title="Your companies">
                        {isLoading ? (
                            <Typography variant="body2" color="text.secondary">
                                Loading…
                            </Typography>
                        ) : companies.length === 0 ? (
                            <EmptyState
                                title="No companies yet"
                                description="Create one to start scoping memory above the project level."
                            />
                        ) : (
                            <TextField
                                select
                                size="small"
                                fullWidth
                                label="Active company"
                                value={selectedId ?? ""}
                                onChange={(e) => setSelectedId(e.target.value || null)}
                            >
                                {companies.map((company) => (
                                    <MenuItem key={company.id} value={company.id}>
                                        {company.name} ({company.slug})
                                    </MenuItem>
                                ))}
                            </TextField>
                        )}
                    </SectionCard>
                </Stack>

                <Stack spacing={2}>
                    {selected ? (
                        <SectionCard
                            title={selected.name}
                            description="Company brief loads as an always-on context packet section (cap 500 chars)."
                            action={
                                <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap alignItems="center">
                                    <Button
                                        component={RouterLink}
                                        to={`/companies/${selected.id}/memory`}
                                        size="small"
                                        variant="outlined"
                                    >
                                        Company semantic
                                    </Button>
                                    <Chip
                                        size="small"
                                        variant="outlined"
                                        label={`Slug: ${selected.slug}`}
                                    />
                                    <Chip
                                        size="small"
                                        variant="outlined"
                                        label={`Updated ${formatDateTime(selected.updated_at)}`}
                                    />
                                </Stack>
                            }
                        >
                            <Stack spacing={2}>
                                <TextField
                                    label="Name"
                                    value={editedName}
                                    onChange={(e) => setEditedName(e.target.value)}
                                    inputProps={{ maxLength: 255 }}
                                />
                                <Divider />
                                <Typography variant="subtitle2">Company brief</Typography>
                                <Typography variant="caption" color="text.secondary">
                                    Short, always-on summary: mission, stack, policies, coding
                                    standards. First {BRIEF_MAX_CHARS} chars are injected into every
                                    run.
                                </Typography>
                                <TextField
                                    value={brief}
                                    onChange={(e) => setBrief(e.target.value)}
                                    multiline
                                    minRows={10}
                                    inputProps={{ maxLength: 4000 }}
                                    placeholder="e.g. Company glossary, deploy rules, security standards."
                                />
                                <Stack direction="row" justifyContent="space-between" alignItems="center">
                                    <Typography
                                        variant="caption"
                                        color={brief.length > BRIEF_MAX_CHARS ? "error.main" : "text.secondary"}
                                    >
                                        {brief.length} chars · injected: {Math.min(brief.length, BRIEF_MAX_CHARS)}
                                    </Typography>
                                    <Button
                                        variant="contained"
                                        disabled={updateMut.isPending}
                                        onClick={() => updateMut.mutate()}
                                    >
                                        Save company
                                    </Button>
                                </Stack>
                                {updateMut.isError && (
                                    <Alert severity="error">
                                        {updateMut.error instanceof Error
                                            ? updateMut.error.message
                                            : "Couldn't save."}
                                    </Alert>
                                )}
                            </Stack>
                        </SectionCard>
                    ) : (
                        <Paper sx={{ p: 4, borderRadius: 4 }}>
                            <EmptyState
                                title="Pick a company"
                                description="Select one on the left, or create your first company."
                            />
                        </Paper>
                    )}
                </Stack>
            </Box>
        </PageShell>
    );
}
