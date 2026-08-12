import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useForm, Controller } from "react-hook-form";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
    Alert,
    Box,
    Button,
    Chip,
    CircularProgress,
    Divider,
    FormControl,
    FormHelperText,
    InputLabel,
    MenuItem,
    Paper,
    Select,
    Stack,
    TextField,
    Typography,
} from "@mui/material";
import { Save as SaveIcon, Publish as PublishIcon, CheckCircle as CheckIcon } from "@mui/icons-material";
import {
    createSkillDraft,
    getSkillDraft,
    publishSkillDraft,
    updateSkillDraft,
    validateSkillDraft,
    type SkillDraft,
    type SkillDraftCreatePayload,
    type SkillScope,
} from "../../api/workforce";
import { getDefaultCompany } from "../../api/companies";
import { useSnackbar } from "../../app/snackbarContext";
import { PageShell } from "../../components/ui/PageShell";

type SkillBuilderForm = {
    name: string;
    slug: string;
    target_scope: SkillScope;
    purpose: string;
    when_to_use: string;
    capabilities: string;
    inputs: string;
    outputs: string;
    instructions: string;
    tools: string;
    knowledge: string;
    constraints: string;
    risk_level: string;
    examples: string;
    evaluation_criteria: string;
};

function parseJsonSafe(value: string, fallback: Record<string, unknown> = {}) {
    if (!value.trim()) return fallback;
    try {
        return JSON.parse(value);
    } catch {
        return fallback;
    }
}

function parseListSafe(value: string): string[] {
    return value
        .split("\n")
        .map((line) => line.trim())
        .filter(Boolean);
}

export default function SkillBuilderPage() {
    const [searchParams] = useSearchParams();
    const draftId = searchParams.get("draftId");
    const navigate = useNavigate();
    const queryClient = useQueryClient();
    const { showToast } = useSnackbar();

    const [validationResult, setValidationResult] = useState<SkillDraft | null>(null);

    const { data: defaultCompany } = useQuery({
        queryKey: ["companies", "default"],
        queryFn: getDefaultCompany,
    });

    const {
        control,
        register,
        handleSubmit,
        reset,
        formState: { errors },
    } = useForm<SkillBuilderForm>({
        defaultValues: {
            name: "",
            slug: "",
            target_scope: "organization",
            purpose: "",
            when_to_use: "",
            capabilities: "",
            inputs: "{}",
            outputs: "{}",
            instructions: "",
            tools: "",
            knowledge: "",
            constraints: "",
            risk_level: "low",
            examples: "",
            evaluation_criteria: "",
        },
    });

    const { data: loadedDraft, isLoading: isLoadingDraft } = useQuery({
        queryKey: ["workforce", "skill-draft", draftId],
        queryFn: () => getSkillDraft(draftId!),
        enabled: Boolean(draftId),
    });

    useEffect(() => {
        if (!loadedDraft) return;
        reset({
            name: loadedDraft.name,
            slug: loadedDraft.slug,
            target_scope: loadedDraft.scope || loadedDraft.target_scope || "organization",
            purpose: loadedDraft.purpose,
            when_to_use: loadedDraft.when_to_use,
            capabilities: loadedDraft.capabilities.join("\n"),
            inputs: JSON.stringify(loadedDraft.inputs, null, 2),
            outputs: JSON.stringify(loadedDraft.outputs, null, 2),
            instructions: loadedDraft.instructions,
            tools: loadedDraft.tools.join("\n"),
            knowledge: loadedDraft.knowledge.join("\n"),
            constraints: loadedDraft.constraints.join("\n"),
            risk_level: loadedDraft.risk_level,
            examples: loadedDraft.examples.join("\n"),
            evaluation_criteria: loadedDraft.evaluation_criteria.join("\n"),
        });
    }, [loadedDraft, reset]);

    const draftValidation = validationResult ?? loadedDraft ?? null;

    const createMutation = useMutation({
        mutationFn: (payload: SkillDraftCreatePayload) => createSkillDraft(payload),
        onSuccess: (data) => {
            showToast({ message: "Draft saved successfully", severity: "success" });
            queryClient.invalidateQueries({ queryKey: ["workforce", "skill-drafts"] });
            navigate(`/skills/builder?draftId=${data.id}`);
        },
        onError: (error: Error) => {
            showToast({ message: `Save failed: ${error.message}`, severity: "error" });
        },
    });

    const updateMutation = useMutation({
        mutationFn: (payload: SkillDraftCreatePayload) =>
            updateSkillDraft(draftId!, payload),
        onSuccess: (data) => {
            showToast({ message: "Draft updated successfully", severity: "success" });
            queryClient.invalidateQueries({ queryKey: ["workforce", "skill-draft", draftId] });
            setValidationResult(data);
        },
        onError: (error: Error) => {
            showToast({ message: `Update failed: ${error.message}`, severity: "error" });
        },
    });

    const validateMutation = useMutation({
        mutationFn: () => validateSkillDraft(draftId!),
        onSuccess: (data) => {
            setValidationResult(data);
            if (data.is_valid) {
                showToast({ message: "Skill is valid!", severity: "success" });
            } else {
                showToast({
                    message: `Validation found ${data.validation_errors.length} error(s)`,
                    severity: "warning",
                });
            }
        },
        onError: (error: Error) => {
            showToast({ message: `Validation failed: ${error.message}`, severity: "error" });
        },
    });

    const publishMutation = useMutation({
        mutationFn: () => publishSkillDraft(draftId!),
        onSuccess: () => {
            showToast({ message: "Skill published successfully!", severity: "success" });
            queryClient.invalidateQueries({ queryKey: ["workforce", "skills"] });
            navigate("/skills");
        },
        onError: (error: Error) => {
            showToast({ message: `Publish failed: ${error.message}`, severity: "error" });
        },
    });

    const onSave = (data: SkillBuilderForm) => {
        const payload: SkillDraftCreatePayload = {
            company_id: defaultCompany?.id ?? null,
            name: data.name,
            slug: data.slug,
            scope: data.target_scope,
            purpose: data.purpose,
            when_to_use: data.when_to_use,
            capabilities: parseListSafe(data.capabilities),
            inputs: parseJsonSafe(data.inputs),
            outputs: parseJsonSafe(data.outputs),
            instructions: data.instructions,
            tools: parseListSafe(data.tools),
            knowledge: parseListSafe(data.knowledge),
            constraints: parseListSafe(data.constraints),
            risk_level: data.risk_level,
            examples: parseListSafe(data.examples),
            evaluation_criteria: parseListSafe(data.evaluation_criteria),
        };

        if (draftId) {
            updateMutation.mutate(payload);
        } else {
            createMutation.mutate(payload);
        }
    };

    const isSaving = createMutation.isPending || updateMutation.isPending;
    const isPublishing = publishMutation.isPending;
    const isValidating = validateMutation.isPending;

    if (draftId && isLoadingDraft) {
        return (
            <PageShell>
                <Stack alignItems="center" spacing={2} sx={{ py: 8 }}>
                    <CircularProgress />
                    <Typography color="text.secondary">Loading draft...</Typography>
                </Stack>
            </PageShell>
        );
    }

    return (
        <PageShell maxWidth="md">
            <Stack spacing={3} sx={{ py: 4 }}>
                <Box>
                    <Typography variant="h4" gutterBottom>
                        {draftId ? "Edit Skill Draft" : "Create Skill"}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                        Define a reusable skill that agents can learn and apply
                    </Typography>
                </Box>

                {draftValidation && (
                    <Stack spacing={2}>
                        {draftValidation.validation_errors.length > 0 && (
                            <Alert severity="error">
                                <Typography variant="subtitle2" gutterBottom>
                                    Validation Errors
                                </Typography>
                                <ul style={{ margin: 0, paddingLeft: 20 }}>
                                    {draftValidation.validation_errors.map((error, idx) => (
                                        <li key={idx}>{error}</li>
                                    ))}
                                </ul>
                            </Alert>
                        )}
                        {draftValidation.validation_warnings.length > 0 && (
                            <Alert severity="warning">
                                <Typography variant="subtitle2" gutterBottom>
                                    Warnings
                                </Typography>
                                <ul style={{ margin: 0, paddingLeft: 20 }}>
                                    {draftValidation.validation_warnings.map((warning, idx) => (
                                        <li key={idx}>{warning}</li>
                                    ))}
                                </ul>
                            </Alert>
                        )}
                        {draftValidation.duplicate_matches.length > 0 && (
                            <Alert severity="info">
                                <Typography variant="subtitle2" gutterBottom>
                                    Similar Skills Found
                                </Typography>
                                <Stack spacing={1}>
                                    {draftValidation.duplicate_matches.map((match) => (
                                        <Box key={match.skill_id}>
                                            <Typography variant="body2">
                                                {match.skill_name} -{" "}
                                                <Chip
                                                    label={`${Math.round(match.similarity * 100)}% similar`}
                                                    size="small"
                                                />
                                            </Typography>
                                        </Box>
                                    ))}
                                </Stack>
                            </Alert>
                        )}
                        {draftValidation.is_valid && (
                            <Alert severity="success" icon={<CheckIcon />}>
                                This skill is valid and ready to publish
                            </Alert>
                        )}
                    </Stack>
                )}

                <Paper sx={{ p: 3 }}>
                    <form onSubmit={handleSubmit(onSave)}>
                        <Stack spacing={3}>
                            <TextField
                                label="Skill Name"
                                fullWidth
                                required
                                {...register("name", { required: "Name is required" })}
                                error={Boolean(errors.name)}
                                helperText={errors.name?.message}
                            />

                            <TextField
                                label="Slug"
                                fullWidth
                                required
                                {...register("slug", {
                                    required: "Slug is required",
                                    pattern: {
                                        value: /^[a-z0-9-]+$/,
                                        message: "Slug must be lowercase alphanumeric with hyphens",
                                    },
                                })}
                                error={Boolean(errors.slug)}
                                helperText={
                                    errors.slug?.message ||
                                    "Lowercase alphanumeric with hyphens (e.g., python-testing)"
                                }
                            />

                            <FormControl fullWidth>
                                <InputLabel>Scope</InputLabel>
                                <Controller
                                    name="target_scope"
                                    control={control}
                                    render={({ field }) => (
                                        <Select {...field} label="Scope">
                                            <MenuItem value="task">Task</MenuItem>
                                            <MenuItem value="project">Project</MenuItem>
                                            <MenuItem value="organization">Organization</MenuItem>
                                        </Select>
                                    )}
                                />
                                <FormHelperText>
                                    Who can use this skill (task, project, or organization-wide)
                                </FormHelperText>
                            </FormControl>

                            <TextField
                                label="Purpose"
                                fullWidth
                                required
                                multiline
                                rows={2}
                                {...register("purpose", { required: "Purpose is required" })}
                                error={Boolean(errors.purpose)}
                                helperText={
                                    errors.purpose?.message || "What does this skill accomplish?"
                                }
                            />

                            <TextField
                                label="When to Use"
                                fullWidth
                                required
                                multiline
                                rows={2}
                                {...register("when_to_use", {
                                    required: "When to use is required",
                                })}
                                error={Boolean(errors.when_to_use)}
                                helperText={
                                    errors.when_to_use?.message ||
                                    "When should an agent apply this skill?"
                                }
                            />

                            <TextField
                                label="Capabilities"
                                fullWidth
                                multiline
                                rows={3}
                                {...register("capabilities")}
                                helperText="One capability per line (e.g., python, testing, api)"
                            />

                            <Divider />

                            <TextField
                                label="Inputs (JSON)"
                                fullWidth
                                multiline
                                rows={4}
                                {...register("inputs")}
                                helperText="JSON object defining expected inputs"
                            />

                            <TextField
                                label="Outputs (JSON)"
                                fullWidth
                                multiline
                                rows={4}
                                {...register("outputs")}
                                helperText="JSON object defining expected outputs"
                            />

                            <Divider />

                            <TextField
                                label="Instructions"
                                fullWidth
                                multiline
                                rows={6}
                                {...register("instructions")}
                                helperText="Detailed instructions for executing this skill"
                            />

                            <TextField
                                label="Tools"
                                fullWidth
                                multiline
                                rows={3}
                                {...register("tools")}
                                helperText="One tool per line (e.g., pytest, git, curl)"
                            />

                            <TextField
                                label="Knowledge Requirements"
                                fullWidth
                                multiline
                                rows={3}
                                {...register("knowledge")}
                                helperText="One knowledge item per line"
                            />

                            <TextField
                                label="Constraints"
                                fullWidth
                                multiline
                                rows={3}
                                {...register("constraints")}
                                helperText="One constraint per line"
                            />

                            <FormControl fullWidth>
                                <InputLabel>Risk Level</InputLabel>
                                <Controller
                                    name="risk_level"
                                    control={control}
                                    render={({ field }) => (
                                        <Select {...field} label="Risk Level">
                                            <MenuItem value="low">Low</MenuItem>
                                            <MenuItem value="medium">Medium</MenuItem>
                                            <MenuItem value="high">High</MenuItem>
                                        </Select>
                                    )}
                                />
                            </FormControl>

                            <TextField
                                label="Examples"
                                fullWidth
                                multiline
                                rows={4}
                                {...register("examples")}
                                helperText="One example per line"
                            />

                            <TextField
                                label="Evaluation Criteria"
                                fullWidth
                                multiline
                                rows={3}
                                {...register("evaluation_criteria")}
                                helperText="One criterion per line"
                            />

                            <Divider />

                            <Stack direction="row" spacing={2}>
                                <Button
                                    type="submit"
                                    variant="contained"
                                    startIcon={isSaving ? <CircularProgress size={16} /> : <SaveIcon />}
                                    disabled={isSaving || isPublishing}
                                >
                                    Save Draft
                                </Button>
                                {draftId && (
                                    <>
                                        <Button
                                            variant="outlined"
                                            startIcon={
                                                isValidating ? <CircularProgress size={16} /> : <CheckIcon />
                                            }
                                            onClick={() => validateMutation.mutate()}
                                            disabled={isValidating || isSaving || isPublishing}
                                        >
                                            Validate
                                        </Button>
                                        <Button
                                            variant="contained"
                                            color="success"
                                            startIcon={
                                                isPublishing ? <CircularProgress size={16} /> : <PublishIcon />
                                            }
                                            onClick={() => publishMutation.mutate()}
                                            disabled={
                                                isPublishing ||
                                                isSaving ||
                                                !draftValidation?.is_valid
                                            }
                                        >
                                            Publish
                                        </Button>
                                    </>
                                )}
                                <Box sx={{ flex: 1 }} />
                                <Button variant="text" onClick={() => navigate("/skills")}>
                                    Cancel
                                </Button>
                            </Stack>
                        </Stack>
                    </form>
                </Paper>
            </Stack>
        </PageShell>
    );
}
