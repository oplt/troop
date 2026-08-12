import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
    Box,
    Button,
    Chip,
    Dialog,
    DialogActions,
    DialogContent,
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
    Archive as ArchiveIcon,
    Edit as EditIcon,
    Business as DepartmentIcon,
} from "@mui/icons-material";
import {
    archiveDepartment,
    createDepartment,
    listDepartments,
    updateDepartment,
    type Department,
    type DepartmentCreatePayload,
} from "../api/workforce";
import { getDefaultCompany } from "../api/companies";
import { useSnackbar } from "../app/snackbarContext";
import { EmptyState } from "../components/ui/EmptyState";
import { PageShell } from "../components/ui/PageShell";
import { SectionCard } from "../components/ui/SectionCard";
import { formatDateTime } from "../utils/formatters";

type DepartmentFormData = {
    name: string;
    slug: string;
    description: string;
    parent_department_id: string;
};

export default function DepartmentsPage() {
    const queryClient = useQueryClient();
    const { showToast } = useSnackbar();
    const [createDialogOpen, setCreateDialogOpen] = useState(false);
    const [editingDepartment, setEditingDepartment] = useState<Department | null>(null);
    const [formData, setFormData] = useState<DepartmentFormData>({
        name: "",
        slug: "",
        description: "",
        parent_department_id: "",
    });

    const { data: defaultCompany, isLoading: isLoadingCompany } = useQuery({
        queryKey: ["companies", "default"],
        queryFn: getDefaultCompany,
    });

    const {
        data: departments = [],
        isLoading: isLoadingDepartments,
        error,
    } = useQuery({
        queryKey: ["workforce", "departments", defaultCompany?.id],
        queryFn: () => listDepartments(defaultCompany!.id),
        enabled: Boolean(defaultCompany),
    });

    const createMutation = useMutation({
        mutationFn: (payload: DepartmentCreatePayload) => createDepartment(payload),
        onSuccess: () => {
            showToast({ message: "Department created successfully", severity: "success" });
            queryClient.invalidateQueries({
                queryKey: ["workforce", "departments", defaultCompany?.id],
            });
            handleCloseDialog();
        },
        onError: (error: Error) => {
            showToast({ message: `Failed to create: ${error.message}`, severity: "error" });
        },
    });

    const updateMutation = useMutation({
        mutationFn: ({
            id,
            payload,
        }: {
            id: string;
            payload: { name?: string; description?: string | null; parent_department_id?: string | null };
        }) => updateDepartment(id, payload),
        onSuccess: () => {
            showToast({ message: "Department updated successfully", severity: "success" });
            queryClient.invalidateQueries({
                queryKey: ["workforce", "departments", defaultCompany?.id],
            });
            handleCloseDialog();
        },
        onError: (error: Error) => {
            showToast({ message: `Failed to update: ${error.message}`, severity: "error" });
        },
    });

    const archiveMutation = useMutation({
        mutationFn: (id: string) => archiveDepartment(id),
        onSuccess: () => {
            showToast({ message: "Department archived", severity: "success" });
            queryClient.invalidateQueries({
                queryKey: ["workforce", "departments", defaultCompany?.id],
            });
        },
        onError: (error: Error) => {
            showToast({ message: `Failed to archive: ${error.message}`, severity: "error" });
        },
    });

    const handleOpenCreate = () => {
        setEditingDepartment(null);
        setFormData({
            name: "",
            slug: "",
            description: "",
            parent_department_id: "",
        });
        setCreateDialogOpen(true);
    };

    const handleOpenEdit = (dept: Department) => {
        setEditingDepartment(dept);
        setFormData({
            name: dept.name,
            slug: dept.slug,
            description: dept.description || "",
            parent_department_id: dept.parent_department_id || "",
        });
        setCreateDialogOpen(true);
    };

    const handleCloseDialog = () => {
        setCreateDialogOpen(false);
        setEditingDepartment(null);
        setFormData({
            name: "",
            slug: "",
            description: "",
            parent_department_id: "",
        });
    };

    const handleSubmit = () => {
        if (!defaultCompany) return;

        if (editingDepartment) {
            updateMutation.mutate({
                id: editingDepartment.id,
                payload: {
                    name: formData.name,
                    description: formData.description || null,
                    parent_department_id: formData.parent_department_id || null,
                },
            });
        } else {
            createMutation.mutate({
                company_id: defaultCompany.id,
                name: formData.name,
                slug: formData.slug,
                description: formData.description || null,
                parent_department_id: formData.parent_department_id || null,
            });
        }
    };

    const activeDepartments = departments.filter((d) => !d.is_archived);
    const isLoading = isLoadingCompany || isLoadingDepartments;

    return (
        <PageShell maxWidth="lg">
            <Stack spacing={3} sx={{ py: 4 }}>
                <Stack direction="row" alignItems="center" justifyContent="space-between">
                    <Box>
                        <Typography variant="h4" gutterBottom>
                            Departments
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                            Organize your workforce into departments and teams
                        </Typography>
                    </Box>
                    <Button
                        variant="contained"
                        startIcon={<AddIcon />}
                        onClick={handleOpenCreate}
                        disabled={!defaultCompany}
                    >
                        Create Department
                    </Button>
                </Stack>

                {error && (
                    <SectionCard>
                        <Typography color="error">
                            Error loading departments: {(error as Error).message}
                        </Typography>
                    </SectionCard>
                )}

                {isLoading ? (
                    <SectionCard>
                        <LinearProgress />
                    </SectionCard>
                ) : activeDepartments.length === 0 ? (
                    <EmptyState
                        icon={<DepartmentIcon sx={{ fontSize: 64 }} />}
                        title="No departments yet"
                        description="Create your first department to start organizing your workforce"
                        action={
                            <Button
                                variant="contained"
                                startIcon={<AddIcon />}
                                onClick={handleOpenCreate}
                            >
                                Create Department
                            </Button>
                        }
                    />
                ) : (
                    <TableContainer component={Paper}>
                        <Table>
                            <TableHead>
                                <TableRow>
                                    <TableCell>Name</TableCell>
                                    <TableCell>Slug</TableCell>
                                    <TableCell>Description</TableCell>
                                    <TableCell>Parent</TableCell>
                                    <TableCell>Created</TableCell>
                                    <TableCell align="right">Actions</TableCell>
                                </TableRow>
                            </TableHead>
                            <TableBody>
                                {activeDepartments.map((dept) => {
                                    const parent = departments.find(
                                        (d) => d.id === dept.parent_department_id,
                                    );
                                    return (
                                        <TableRow key={dept.id} hover>
                                            <TableCell>
                                                <Typography variant="body2" fontWeight={600}>
                                                    {dept.name}
                                                </Typography>
                                            </TableCell>
                                            <TableCell>
                                                <Chip label={dept.slug} size="small" variant="outlined" />
                                            </TableCell>
                                            <TableCell>
                                                <Typography variant="body2" color="text.secondary">
                                                    {dept.description || "—"}
                                                </Typography>
                                            </TableCell>
                                            <TableCell>
                                                {parent ? (
                                                    <Chip label={parent.name} size="small" />
                                                ) : (
                                                    "—"
                                                )}
                                            </TableCell>
                                            <TableCell>
                                                <Typography variant="caption" color="text.secondary">
                                                    {formatDateTime(dept.created_at)}
                                                </Typography>
                                            </TableCell>
                                            <TableCell align="right">
                                                <Stack direction="row" spacing={0.5} justifyContent="flex-end">
                                                    <Tooltip title="Edit">
                                                        <IconButton
                                                            size="small"
                                                            onClick={() => handleOpenEdit(dept)}
                                                        >
                                                            <EditIcon fontSize="small" />
                                                        </IconButton>
                                                    </Tooltip>
                                                    <Tooltip title="Archive">
                                                        <IconButton
                                                            size="small"
                                                            onClick={() => archiveMutation.mutate(dept.id)}
                                                        >
                                                            <ArchiveIcon fontSize="small" />
                                                        </IconButton>
                                                    </Tooltip>
                                                </Stack>
                                            </TableCell>
                                        </TableRow>
                                    );
                                })}
                            </TableBody>
                        </Table>
                    </TableContainer>
                )}

                <Dialog open={createDialogOpen} onClose={handleCloseDialog} maxWidth="sm" fullWidth>
                    <DialogTitle>
                        {editingDepartment ? "Edit Department" : "Create Department"}
                    </DialogTitle>
                    <DialogContent>
                        <Stack spacing={2} sx={{ mt: 1 }}>
                            <TextField
                                label="Name"
                                fullWidth
                                required
                                value={formData.name}
                                onChange={(e) =>
                                    setFormData((prev) => ({ ...prev, name: e.target.value }))
                                }
                            />
                            {!editingDepartment && (
                                <TextField
                                    label="Slug"
                                    fullWidth
                                    required
                                    value={formData.slug}
                                    onChange={(e) =>
                                        setFormData((prev) => ({ ...prev, slug: e.target.value }))
                                    }
                                    helperText="Lowercase alphanumeric with hyphens (e.g., engineering)"
                                />
                            )}
                            <TextField
                                label="Description"
                                fullWidth
                                multiline
                                rows={2}
                                value={formData.description}
                                onChange={(e) =>
                                    setFormData((prev) => ({ ...prev, description: e.target.value }))
                                }
                            />
                            <FormControl fullWidth>
                                <InputLabel>Parent Department</InputLabel>
                                <Select
                                    value={formData.parent_department_id}
                                    onChange={(e) =>
                                        setFormData((prev) => ({
                                            ...prev,
                                            parent_department_id: e.target.value,
                                        }))
                                    }
                                    label="Parent Department"
                                >
                                    <MenuItem value="">
                                        <em>None (top-level)</em>
                                    </MenuItem>
                                    {activeDepartments
                                        .filter((d) => d.id !== editingDepartment?.id)
                                        .map((dept) => (
                                            <MenuItem key={dept.id} value={dept.id}>
                                                {dept.name}
                                            </MenuItem>
                                        ))}
                                </Select>
                            </FormControl>
                        </Stack>
                    </DialogContent>
                    <DialogActions>
                        <Button onClick={handleCloseDialog}>Cancel</Button>
                        <Button
                            onClick={handleSubmit}
                            variant="contained"
                            disabled={
                                !formData.name || (!editingDepartment && !formData.slug)
                            }
                        >
                            {editingDepartment ? "Update" : "Create"}
                        </Button>
                    </DialogActions>
                </Dialog>
            </Stack>
        </PageShell>
    );
}
