import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import {
    Box,
    Button,
    Chip,
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
    Paper,
    Select,
    Stack,
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
import { EmptyState } from "../components/ui/EmptyState";
import { PageShell } from "../components/ui/PageShell";
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

    const getScopeColor = (scope: SkillScope) => {
        switch (scope) {
            case "task":
                return "default";
            case "project":
                return "info";
            case "organization":
                return "success";
            case "template":
                return "warning";
            case "global":
                return "error";
            default:
                return "default";
        }
    };

    const getStatusColor = (status: string) => {
        switch (status) {
            case "active":
                return "success";
            case "draft":
                return "warning";
            case "deprecated":
                return "error";
            default:
                return "default";
        }
    };

    return (
        <PageShell maxWidth="lg">
            <Stack spacing={3} sx={{ py: 4 }}>
                <Stack direction="row" alignItems="center" justifyContent="space-between">
                    <Box>
                        <Typography variant="h4" gutterBottom>
                            Skills
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                            Manage reusable skills that agents can learn and apply
                        </Typography>
                    </Box>
                    <Button
                        variant="contained"
                        startIcon={<AddIcon />}
                        onClick={() => navigate("/skills/builder")}
                    >
                        Create Skill
                    </Button>
                </Stack>

                <Stack direction="row" spacing={2}>
                    <TextField
                        placeholder="Search skills..."
                        size="small"
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        sx={{ flex: 1 }}
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
                </Stack>

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
                    <TableContainer component={Paper}>
                        <Table>
                            <TableHead>
                                <TableRow>
                                    <TableCell>Name</TableCell>
                                    <TableCell>Purpose</TableCell>
                                    <TableCell>Scope</TableCell>
                                    <TableCell>Status</TableCell>
                                    <TableCell>Capabilities</TableCell>
                                    <TableCell>Version</TableCell>
                                    <TableCell>Updated</TableCell>
                                    <TableCell align="right">Actions</TableCell>
                                </TableRow>
                            </TableHead>
                            <TableBody>
                                {filteredSkills.map((skill) => (
                                    <TableRow key={skill.id} hover>
                                        <TableCell>
                                            <Typography variant="body2" fontWeight={600}>
                                                {skill.name}
                                            </Typography>
                                            <Typography variant="caption" color="text.secondary">
                                                {skill.slug}
                                            </Typography>
                                        </TableCell>
                                        <TableCell>
                                            <Typography
                                                variant="body2"
                                                color="text.secondary"
                                                sx={{
                                                    maxWidth: 300,
                                                    overflow: "hidden",
                                                    textOverflow: "ellipsis",
                                                    whiteSpace: "nowrap",
                                                }}
                                            >
                                                {skill.purpose}
                                            </Typography>
                                        </TableCell>
                                        <TableCell>
                                            <Chip
                                                label={skill.scope}
                                                size="small"
                                                color={getScopeColor(skill.scope)}
                                            />
                                        </TableCell>
                                        <TableCell>
                                            <Chip
                                                label={skill.status}
                                                size="small"
                                                color={getStatusColor(skill.status)}
                                            />
                                        </TableCell>
                                        <TableCell>
                                            <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
                                                {skill.capabilities.slice(0, 2).map((cap) => (
                                                    <Chip key={cap} label={cap} size="small" />
                                                ))}
                                                {skill.capabilities.length > 2 && (
                                                    <Chip
                                                        label={`+${skill.capabilities.length - 2}`}
                                                        size="small"
                                                        variant="outlined"
                                                    />
                                                )}
                                            </Stack>
                                        </TableCell>
                                        <TableCell>
                                            <Typography variant="caption" color="text.secondary">
                                                v{skill.version}
                                            </Typography>
                                        </TableCell>
                                        <TableCell>
                                            <Typography variant="caption" color="text.secondary">
                                                {formatDateTime(skill.updated_at)}
                                            </Typography>
                                        </TableCell>
                                        <TableCell align="right">
                                            <Stack direction="row" spacing={0.5} justifyContent="flex-end">
                                                <Tooltip title="View details">
                                                    <IconButton size="small">
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
                                        </TableCell>
                                    </TableRow>
                                ))}
                            </TableBody>
                        </Table>
                    </TableContainer>
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
