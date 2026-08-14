import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, Link as RouterLink } from "react-router-dom";
import {
    Box,
    Button,
    Dialog,
    DialogActions,
    DialogContent,
    DialogContentText,
    DialogTitle,
    FormControl,
    IconButton,
    InputLabel,
    LinearProgress,
    MenuItem,
    Select,
    Stack,
    TextField,
    Tooltip,
    Typography,
} from "@mui/material";
import {
    Add as AddIcon,
    TrendingUp as PromoteIcon,
    Visibility as ViewIcon,
    AutoAwesome as SkillIcon,
} from "@mui/icons-material";
import {
    listSkills,
    promoteSkill,
    type Skill,
    type SkillScope,
} from "../api/workforce";
import { useSnackbar } from "../app/snackbarContext";
import { CatalogCard } from "../components/ui/CatalogCard";
import { EmptyState } from "../components/ui/EmptyState";
import { PageShell } from "../components/ui/PageShell";
import { PageHeader } from "../components/ui/PageHeader";
import { FilterToolbar } from "../components/ui/FilterToolbar";
import { SectionCard } from "../components/ui/SectionCard";
import { formatDateTime } from "../utils/formatters";

type PromoteDialogState = {
    open: boolean;
    skill: Skill | null;
    targetScope: SkillScope;
};

export default function SkillsPage() {
    const navigate = useNavigate();
    const queryClient = useQueryClient();
    const { showToast } = useSnackbar();
    const [searchQuery, setSearchQuery] = useState("");
    const [scopeFilter, setScopeFilter] = useState<SkillScope | "all">("all");
    const [promoteDialog, setPromoteDialog] = useState<PromoteDialogState>({
        open: false,
        skill: null,
        targetScope: "organization",
    });

    const {
        data: skills = [],
        isLoading,
        error,
    } = useQuery({
        queryKey: ["workforce", "skills"],
        queryFn: listSkills,
    });

    const promoteMutation = useMutation({
        mutationFn: ({ skillId, scope }: { skillId: string; scope: SkillScope }) =>
            promoteSkill(skillId, scope),
        onSuccess: () => {
            showToast({ message: "Skill promoted successfully", severity: "success" });
            queryClient.invalidateQueries({ queryKey: ["workforce", "skills"] });
            setPromoteDialog({ open: false, skill: null, targetScope: "organization" });
        },
        onError: (error: Error) => {
            showToast({ message: `Failed to promote: ${error.message}`, severity: "error" });
        },
    });

    const handleOpenPromote = (skill: Skill) => {
        const nextScope = skill.scope === "task" ? "project" : "organization";
        setPromoteDialog({
            open: true,
            skill,
            targetScope: nextScope,
        });
    };

    const handlePromote = () => {
        if (promoteDialog.skill) {
            promoteMutation.mutate({
                skillId: promoteDialog.skill.id,
                scope: promoteDialog.targetScope,
            });
        }
    };

    const filteredSkills = skills.filter((skill) => {
        const matchesSearch =
            searchQuery === "" ||
            skill.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
            skill.purpose.toLowerCase().includes(searchQuery.toLowerCase());
        const matchesScope = scopeFilter === "all" || skill.scope === scopeFilter;
        return matchesSearch && matchesScope;
    });

    return (
        <PageShell maxWidth="lg">
            <Stack spacing={3} sx={{ py: 4 }}>
                <PageHeader
                    title="Skills"
                    description="Reusable capabilities agents can learn. Browse Marketplace for packs, or open Agents to attach skills to contracts."
                    actions={
                        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                            <Button component={RouterLink} to="/marketplace" variant="outlined">
                                Marketplace
                            </Button>
                            <Button variant="contained" startIcon={<AddIcon />} onClick={() => navigate("/skills/builder")}>
                                Create Skill
                            </Button>
                        </Stack>
                    }
                />

                <FilterToolbar>
                    <TextField
                        placeholder="Search skills..."
                        size="small"
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        sx={{ flex: 1, minWidth: 200 }}
                    />
                    <FormControl size="small" sx={{ minWidth: 150 }}>
                        <InputLabel>Scope</InputLabel>
                        <Select
                            value={scopeFilter}
                            onChange={(e) => setScopeFilter(e.target.value as SkillScope | "all")}
                            label="Scope"
                        >
                            <MenuItem value="all">All Scopes</MenuItem>
                            <MenuItem value="task">Task</MenuItem>
                            <MenuItem value="project">Project</MenuItem>
                            <MenuItem value="organization">Organization</MenuItem>
                        </Select>
                    </FormControl>
                </FilterToolbar>

                {error && (
                    <SectionCard>
                        <Typography color="error">
                            Error loading skills: {(error as Error).message}
                        </Typography>
                    </SectionCard>
                )}

                {isLoading ? (
                    <SectionCard>
                        <LinearProgress />
                    </SectionCard>
                ) : filteredSkills.length === 0 ? (
                    <EmptyState
                        icon={<SkillIcon sx={{ fontSize: 64 }} />}
                        title={searchQuery || scopeFilter !== "all" ? "No skills found" : "No skills yet"}
                        description={
                            searchQuery || scopeFilter !== "all"
                                ? "Try adjusting your search or filters"
                                : "Create your first skill to start building reusable capabilities"
                        }
                        action={
                            !searchQuery && scopeFilter === "all" ? (
                                <Button
                                    variant="contained"
                                    startIcon={<AddIcon />}
                                    onClick={() => navigate("/skills/builder")}
                                >
                                    Create Skill
                                </Button>
                            ) : undefined
                        }
                    />
                ) : (
                    <Box
                        sx={{
                            display: "grid",
                            gap: 2,
                            gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))",
                        }}
                    >
                        {filteredSkills.map((skill) => (
                            <CatalogCard
                                key={skill.id}
                                title={skill.name}
                                description={skill.purpose || skill.slug}
                                scope={skill.scope}
                                tags={[
                                    skill.status,
                                    ...skill.capabilities.slice(0, 3),
                                    ...(skill.capabilities.length > 3
                                        ? [`+${skill.capabilities.length - 3}`]
                                        : []),
                                    `v${skill.version}`,
                                ]}
                                primaryCta={{
                                    label: "Open",
                                    onClick: () => navigate(`/skills/builder?skill=${skill.id}`),
                                }}
                                secondaryAction={
                                    <Stack direction="row" spacing={0.5} alignItems="center">
                                        <Typography variant="caption" color="text.secondary">
                                            {formatDateTime(skill.updated_at)}
                                        </Typography>
                                        <Tooltip title="View details">
                                            <IconButton size="small" onClick={() => navigate(`/skills/builder?skill=${skill.id}`)}>
                                                <ViewIcon fontSize="small" />
                                            </IconButton>
                                        </Tooltip>
                                        {skill.scope !== "organization" && (
                                            <Tooltip title="Promote skill">
                                                <IconButton
                                                    size="small"
                                                    onClick={() => handleOpenPromote(skill)}
                                                >
                                                    <PromoteIcon fontSize="small" />
                                                </IconButton>
                                            </Tooltip>
                                        )}
                                    </Stack>
                                }
                            />
                        ))}
                    </Box>
                )}

                <Dialog
                    open={promoteDialog.open}
                    onClose={() =>
                        setPromoteDialog({ open: false, skill: null, targetScope: "organization" })
                    }
                >
                    <DialogTitle>Promote Skill</DialogTitle>
                    <DialogContent>
                        <DialogContentText sx={{ mb: 2 }}>
                            Promote "{promoteDialog.skill?.name}" from {promoteDialog.skill?.scope} to{" "}
                            {promoteDialog.targetScope} scope?
                        </DialogContentText>
                        <FormControl fullWidth>
                            <InputLabel>Target Scope</InputLabel>
                            <Select
                                value={promoteDialog.targetScope}
                                onChange={(e) =>
                                    setPromoteDialog((prev) => ({
                                        ...prev,
                                        targetScope: e.target.value as SkillScope,
                                    }))
                                }
                                label="Target Scope"
                            >
                                {promoteDialog.skill?.scope === "task" && (
                                    <MenuItem value="project">Project</MenuItem>
                                )}
                                <MenuItem value="organization">Organization</MenuItem>
                            </Select>
                        </FormControl>
                    </DialogContent>
                    <DialogActions>
                        <Button
                            onClick={() =>
                                setPromoteDialog({ open: false, skill: null, targetScope: "organization" })
                            }
                        >
                            Cancel
                        </Button>
                        <Button onClick={handlePromote} variant="contained" autoFocus>
                            Promote
                        </Button>
                    </DialogActions>
                </Dialog>
            </Stack>
        </PageShell>
    );
}
