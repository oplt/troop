import { useMemo, useState } from "react";
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
import { Business as BusinessIcon } from "@mui/icons-material";
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
import { queryKeys } from "../config/queryKeys";
import { PageHeader } from "../components/ui/PageHeader";

const BRIEF_MAX_CHARS = 500;

function slugify(value: string): string {
    return value
        .toLowerCase()
        .replace(/[^a-z0-9-]+/g, "-")
        .replace(/^-+|-+$/g, "")
        .slice(0, 255);
}

function CompanyEditor({ company }: { company: Company }) {
    const queryClient = useQueryClient();
    const { showToast } = useSnackbar();
    const [brief, setBrief] = useState(company.brief_markdown ?? "");
    const [editedName, setEditedName] = useState(company.name);

    const updateMut = useMutation({
        mutationFn: () =>
            updateCompany(company.id, {
                name: editedName.trim() || company.name,
                brief_markdown: brief.slice(0, BRIEF_MAX_CHARS),
            }),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: queryKeys.companies.root });
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
        <SectionCard
            title={company.name}
                    description="A short company brief is included in every run (up to 500 characters)."
            action={
                <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap alignItems="center">
                    <Button
                        component={RouterLink}
                        to={`/companies/${company.id}/memory`}
                        size="small"
                        variant="outlined"
                    >
                        Company semantic
                    </Button>
                    <Chip
                        size="small"
                        variant="outlined"
                        label={`Slug: ${company.slug}`}
                    />
                    <Chip
                        size="small"
                        variant="outlined"
                        label={`Updated ${formatDateTime(company.updated_at)}`}
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
                    Keep the mission, stack, policies, and coding standards concise.
                    Only the first {BRIEF_MAX_CHARS} characters enter each run.
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
    );
}

export function CompaniesPanel() {
    const queryClient = useQueryClient();
    const { showToast } = useSnackbar();
    const [selectedId, setSelectedId] = useState<string | null>(null);
    const [newName, setNewName] = useState("");
    const [newSlug, setNewSlug] = useState("");
    const [companyQuery, setCompanyQuery] = useState("");

    const { data: companies = [], isLoading } = useQuery({
        queryKey: queryKeys.companies.root,
        queryFn: listCompanies,
    });

    const filteredCompanies = useMemo(() => {
        const q = companyQuery.trim().toLowerCase();
        if (!q) return companies;
        return companies.filter(
            (c) => c.name.toLowerCase().includes(q) || c.slug.toLowerCase().includes(q),
        );
    }, [companies, companyQuery]);

    const selected: Company | undefined = useMemo(
        () => filteredCompanies.find((c) => c.id === selectedId) ?? filteredCompanies[0] ?? companies.find((c) => c.id === selectedId),
        [filteredCompanies, companies, selectedId],
    );

    const createMut = useMutation({
        mutationFn: () =>
            createCompany({
                name: newName.trim(),
                slug: slugify(newSlug || newName),
                brief_markdown: "",
            }),
        onSuccess: async (company) => {
            await queryClient.invalidateQueries({ queryKey: queryKeys.companies.root });
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

    return (
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
                            icon={<BusinessIcon />}
                            title="No companies yet"
                            description="Create one to start scoping memory above the project level."
                        />
                    ) : (
                        <Stack spacing={1.5}>
                            <TextField
                                size="small"
                                fullWidth
                                label="Search companies"
                                value={companyQuery}
                                onChange={(e) => setCompanyQuery(e.target.value)}
                                placeholder="Name or slug"
                            />
                            {filteredCompanies.length === 0 ? (
                                <Typography variant="body2" color="text.secondary">
                                    No companies match “{companyQuery}”.
                                </Typography>
                            ) : (
                                <TextField
                                    select
                                    size="small"
                                    fullWidth
                                    label="Active company"
                                    value={selected?.id ?? ""}
                                    onChange={(e) => setSelectedId(e.target.value || null)}
                                >
                                    {filteredCompanies.map((company) => (
                                        <MenuItem key={company.id} value={company.id}>
                                            {company.name} ({company.slug})
                                        </MenuItem>
                                    ))}
                                </TextField>
                            )}
                        </Stack>
                    )}
                </SectionCard>
            </Stack>

            <Stack spacing={2}>
                {selected ? (
                    <CompanyEditor key={selected.id} company={selected} />
                ) : (
                    <Paper sx={{ p: 4, borderRadius: 4 }}>
                        <EmptyState
                            icon={<BusinessIcon />}
                            title="Pick a company"
                            description="Select one on the left, or create your first company."
                        />
                    </Paper>
                )}
            </Stack>
        </Box>
    );
}

export default function CompaniesPage() {
    return (
        <PageShell maxWidth="xl">
            <PageHeader
                eyebrow="Workspace"
                title="Companies"
                description="Keep company-wide context separate from project memory."
            />
            <CompaniesPanel />
        </PageShell>
    );
}
