import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Drawer, Stack, TextField, Typography } from "@mui/material";
import { CloudUpload as UploadIcon } from "@mui/icons-material";

import type { AgentTemplate, SkillPack, TeamTemplate } from "../../api/orchestration";
import {
    createAgentTemplate,
    createSkillPack,
    createTeamTemplate,
    deleteAgentTemplate,
    deleteSkillPack,
    deleteTeamTemplate,
    listTeamTemplates,
    updateAgentTemplate,
    updateSkillPack,
    updateTeamTemplate,
} from "../../api/orchestration";
import { TemplateBrowseView } from "./TemplateBrowseView";
import { TemplateBuilderView } from "./TemplateBuilderView";
import { TemplateDetailDrawer } from "./TemplateDetailDrawer";
import { TemplateFilterToolbar, type FilterOptionGroup } from "./TemplateFilterToolbar";
import { TemplateTopBar } from "./TemplateTopBar";
import {
    buildAgentTemplateFromForm,
    buildInheritancePreview,
    buildTemplateBuilderForm,
    createUniqueSlug,
    EMPTY_TEMPLATE_BUILDER_FORM,
    mergeUnique,
    parseSkillMarkdownDocument,
    parseCsv,
} from "./templateBuilderState";
import type {
    SkillBuilderFormState,
    TemplateFilterState,
    TemplateTabProps,
} from "./types";

const DEFAULT_FILTERS: TemplateFilterState = {
    type: "all",
    roles: [],
    domains: [],
    outcomes: [],
    tools: [],
    autonomy: [],
    visibility: [],
    sortBy: "Newest",
};

const EMPTY_SKILL_FORM: SkillBuilderFormState = {
    name: "",
    description: "",
    capabilities: "",
};

function buildSkillForm(skill?: SkillPack, duplicate = false): SkillBuilderFormState {
    if (!skill) {
        return EMPTY_SKILL_FORM;
    }

    return {
        name: duplicate ? `${skill.name} copy` : skill.name,
        description: skill.description,
        capabilities: skill.capabilities.join(", "),
    };
}

function createTeamCanvasName(existingCount: number) {
    return `Empty team canvas ${existingCount + 1}`;
}

function readFileAsText(file: File) {
    if (typeof file.text === "function") {
        return file.text();
    }

    return new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result ?? ""));
        reader.onerror = () => reject(reader.error ?? new Error("Failed to read file."));
        reader.readAsText(file);
    });
}

function omitId<T extends { id?: string }>(value: T): Omit<T, "id"> {
    const { id, ...rest } = value;
    void id;
    return rest;
}

export function TemplateTab(props: TemplateTabProps) {
    const queryClient = useQueryClient();
    const createTemplateMutation = useMutation({
        mutationFn: createAgentTemplate,
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "agent-templates"] });
        },
    });

    const deleteTemplateMutation = useMutation({
        mutationFn: deleteAgentTemplate,
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "agent-templates"] });
        },
    });
    const updateTemplateMutation = useMutation({
        mutationFn: ({ slug, payload }: { slug: string; payload: Partial<Omit<AgentTemplate, "id">> }) =>
            updateAgentTemplate(slug, payload),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "agent-templates"] });
        },
    });
    const createSkillMutation = useMutation({
        mutationFn: createSkillPack,
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "skill-catalog"] });
        },
    });
    const updateSkillMutation = useMutation({
        mutationFn: ({ slug, payload }: { slug: string; payload: Partial<Omit<SkillPack, "id" | "slug">> }) =>
            updateSkillPack(slug, payload),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "skill-catalog"] });
        },
    });
    const deleteSkillMutation = useMutation({
        mutationFn: deleteSkillPack,
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "skill-catalog"] });
        },
    });
    const { data: teamTemplates = [] } = useQuery({
        queryKey: ["orchestration", "team-templates"],
        queryFn: listTeamTemplates,
    });
    const createTeamTemplateMutation = useMutation({
        mutationFn: createTeamTemplate,
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "team-templates"] });
        },
    });
    const updateTeamTemplateMutation = useMutation({
        mutationFn: ({ id, payload }: { id: string; payload: Partial<Omit<TeamTemplate, "id" | "slug">> }) =>
            updateTeamTemplate(id, payload),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "team-templates"] });
        },
    });
    const deleteTeamTemplateMutation = useMutation({
        mutationFn: deleteTeamTemplate,
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "team-templates"] });
        },
    });
    const [selectedTemplateSlug, setSelectedTemplateSlug] = useState("");
    const [detailsOpen, setDetailsOpen] = useState(false);
    const [searchQuery, setSearchQuery] = useState("");
    const [filters, setFilters] = useState<TemplateFilterState>(DEFAULT_FILTERS);
    const [agentBuilderOpen, setAgentBuilderOpen] = useState(false);
    const [editingAgentTemplateSlug, setEditingAgentTemplateSlug] = useState<string | null>(null);
    const [skillBuilderOpen, setSkillBuilderOpen] = useState(false);
    const [editingSkillSlug, setEditingSkillSlug] = useState<string | null>(null);
    const [skillBuilderBase, setSkillBuilderBase] = useState<SkillPack | null>(null);
    const [skillForm, setSkillForm] = useState<SkillBuilderFormState>(EMPTY_SKILL_FORM);

    const agentTemplates = props.templates;

    const skillCatalog = props.skills;

    const selectedTemplate = useMemo(
        () => agentTemplates.find((item) => item.slug === selectedTemplateSlug) ?? null,
        [agentTemplates, selectedTemplateSlug],
    );

    const templatePreview = useMemo(
        () => buildInheritancePreview(props.form, agentTemplates, skillCatalog),
        [agentTemplates, props.form, skillCatalog],
    );

    const toolbarGroups = useMemo<FilterOptionGroup[]>(
        () => [
            { key: "type", label: "Type", options: ["agent", "team", "skill"] },
            {
                key: "roles",
                label: "Role",
                options: Array.from(new Set([...agentTemplates.map((item) => item.role), ...teamTemplates.flatMap((item) => item.roles)])).sort(),
            },
            {
                key: "domains",
                label: "Domain",
                options: Array.from(new Set(agentTemplates.flatMap((item) => item.tags))).sort(),
            },
            {
                key: "outcomes",
                label: "Outcome",
                options: Array.from(new Set([...agentTemplates.flatMap((item) => item.capabilities), ...teamTemplates.map((item) => item.outcome)])).sort(),
            },
            {
                key: "tools",
                label: "Tool access",
                options: Array.from(new Set([...agentTemplates.flatMap((item) => item.allowed_tools), ...teamTemplates.flatMap((item) => item.tools)])).sort(),
            },
            {
                key: "autonomy",
                label: "Autonomy",
                options: Array.from(new Set(teamTemplates.map((item) => item.autonomy))).sort(),
            },
            {
                key: "visibility",
                label: "Visibility",
                options: Array.from(new Set(teamTemplates.map((item) => item.visibility))).sort(),
            },
            { key: "sortBy", label: "Sort by", options: ["Newest", "Most used", "A-Z"], single: true },
        ],
        [agentTemplates, teamTemplates],
    );

    function openTemplateDetails(templateSlug: string) {
        setSelectedTemplateSlug(templateSlug);
        setDetailsOpen(true);
    }

    function openAgentBuilder(templateSlug?: string) {
        props.onResetBuilder();
        if (!templateSlug) {
            props.setForm(EMPTY_TEMPLATE_BUILDER_FORM);
            setEditingAgentTemplateSlug(null);
        } else {
            const template = agentTemplates.find((item) => item.slug === templateSlug);
            if (!template) {
                return;
            }
            props.setForm(buildTemplateBuilderForm(template));
            setEditingAgentTemplateSlug(template.slug);
        }
        setDetailsOpen(false);
        setAgentBuilderOpen(true);
    }

    function saveAgentTemplate() {
        const existingTemplate = editingAgentTemplateSlug
            ? agentTemplates.find((item) => item.slug === editingAgentTemplateSlug) ?? null
            : null;
        const takenSlugs = agentTemplates
            .filter((item) => item.slug !== editingAgentTemplateSlug)
            .map((item) => item.slug);
        const slug = existingTemplate?.slug ?? (props.form.slug.trim() || createUniqueSlug(props.form.name || "Untitled template", takenSlugs));
        const nextTemplate = buildAgentTemplateFromForm({ ...props.form, slug }, existingTemplate);

        if (existingTemplate) {
            updateTemplateMutation.mutate({ slug: existingTemplate.slug, payload: omitId(nextTemplate) });
        } else {
            createTemplateMutation.mutate(omitId(nextTemplate) as Omit<AgentTemplate, "id">);
        }

        props.setForm(buildTemplateBuilderForm(nextTemplate));
        setEditingAgentTemplateSlug(nextTemplate.slug);
        setAgentBuilderOpen(false);
    }

    function handleDeleteTemplate(slug: string) {
        deleteTemplateMutation.mutate(slug);
    }

    function openSkillBuilder() {
        setEditingSkillSlug(null);
        setSkillBuilderBase(null);
        setSkillForm(EMPTY_SKILL_FORM);
        setSkillBuilderOpen(true);
    }

    function openSkillBuilderFromCard(skill: SkillPack) {
        setEditingSkillSlug(null);
        setSkillBuilderBase(skill);
        setSkillForm(buildSkillForm(skill, true));
        setSkillBuilderOpen(true);
    }

    function editSkill(skill: SkillPack) {
        setEditingSkillSlug(skill.slug);
        setSkillBuilderBase(skill);
        setSkillForm(buildSkillForm(skill));
        setSkillBuilderOpen(true);
    }

    function saveSkill() {
        const existingSkill = editingSkillSlug ? skillCatalog.find((item) => item.slug === editingSkillSlug) ?? null : null;
        const takenSlugs = skillCatalog
            .filter((item) => item.slug !== editingSkillSlug)
            .map((item) => item.slug);
        const slug = existingSkill?.slug ?? createUniqueSlug(skillForm.name || "Untitled skill", takenSlugs);
        const nextSkill: SkillPack = {
            id: existingSkill?.id,
            slug,
            name: skillForm.name.trim() || existingSkill?.name || skillBuilderBase?.name || "Untitled skill",
            description: skillForm.description.trim(),
            capabilities: parseCsv(skillForm.capabilities),
            allowed_tools: existingSkill?.allowed_tools ?? skillBuilderBase?.allowed_tools ?? [],
            rules_markdown: existingSkill?.rules_markdown ?? skillBuilderBase?.rules_markdown ?? "",
            tags: existingSkill?.tags ?? skillBuilderBase?.tags ?? [],
        };

        if (existingSkill) {
            updateSkillMutation.mutate({
                slug: existingSkill.slug,
                payload: {
                    name: nextSkill.name,
                    description: nextSkill.description,
                    capabilities: nextSkill.capabilities,
                    allowed_tools: nextSkill.allowed_tools,
                    rules_markdown: nextSkill.rules_markdown,
                    tags: nextSkill.tags,
                },
            });
        } else {
            createSkillMutation.mutate(omitId(nextSkill) as Omit<SkillPack, "id">);
        }
        setSkillBuilderOpen(false);
    }

    async function handleSkillMarkdownUpload(file: File) {
        const content = await readFileAsText(file);
        setSkillForm(parseSkillMarkdownDocument(content, file.name));
    }

    function attachSkillToTemplate(templateSlug: string, skillSlug: string) {
        const template = agentTemplates.find((item) => item.slug === templateSlug);
        if (!template) {
            return;
        }
        const nextTemplate = { ...template, skills: mergeUnique(template.skills, [skillSlug]) };
        updateTemplateMutation.mutate({ slug: templateSlug, payload: omitId(nextTemplate) });
        if (agentBuilderOpen && editingAgentTemplateSlug === templateSlug) {
            props.setForm((current) => ({ ...current, skills: mergeUnique(current.skills, [skillSlug]) }));
        }
    }

    function removeSkillFromTemplate(templateSlug: string, skillSlug: string) {
        const template = agentTemplates.find((item) => item.slug === templateSlug);
        if (!template) {
            return;
        }
        const nextTemplate = { ...template, skills: template.skills.filter((item) => item !== skillSlug) };
        updateTemplateMutation.mutate({ slug: templateSlug, payload: omitId(nextTemplate) });
        if (agentBuilderOpen && editingAgentTemplateSlug === templateSlug) {
            props.setForm((current) => ({ ...current, skills: current.skills.filter((item) => item !== skillSlug) }));
        }
    }

    function attachTemplateToTeam(teamTemplateId: string, templateSlug: string) {
        const template = teamTemplates.find((item) => item.id === teamTemplateId);
        if (!template) {
            return;
        }
        updateTeamTemplateMutation.mutate({
            id: teamTemplateId,
            payload: {
                agent_template_slugs: mergeUnique(template.agent_template_slugs, [templateSlug]),
            },
        });
    }

    function removeTemplateFromTeam(teamTemplateId: string, templateSlug: string) {
        const template = teamTemplates.find((item) => item.id === teamTemplateId);
        if (!template) {
            return;
        }
        updateTeamTemplateMutation.mutate({
            id: teamTemplateId,
            payload: {
                agent_template_slugs: template.agent_template_slugs.filter((slug) => slug !== templateSlug),
            },
        });
    }

    function addTeamCanvas() {
        const slug = createUniqueSlug(createTeamCanvasName(teamTemplates.length), teamTemplates.map((item) => item.slug));
        createTeamTemplateMutation.mutate({
            slug,
            name: createTeamCanvasName(teamTemplates.length),
            description: "Empty canvas. Drag agent templates here.",
            outcome: "Custom team",
            roles: [],
            tools: [],
            autonomy: "custom",
            visibility: "private",
            agent_template_slugs: [],
        });
    }

    function handleDeleteSkill(slug: string) {
        deleteSkillMutation.mutate(slug);
    }

    function handleDeleteTeamTemplate(templateId: string) {
        deleteTeamTemplateMutation.mutate(templateId);
    }

    return (
        <Stack spacing={2}>
            <TemplateTopBar
                searchQuery={searchQuery}
                onSearchQueryChange={setSearchQuery}
            />

            <TemplateFilterToolbar value={filters} groups={toolbarGroups} onChange={setFilters} />

            <TemplateBrowseView
                templates={agentTemplates}
                skills={skillCatalog}
                teamTemplates={teamTemplates}
                searchQuery={searchQuery}
                filters={filters}
                onOpenDetails={openTemplateDetails}
                onOpenAgentBuilder={openAgentBuilder}
                onOpenSkillBuilder={openSkillBuilder}
                onAddSkillFromCard={openSkillBuilderFromCard}
                onEditSkill={editSkill}
                onCreateFromTemplate={props.onCreateFromTemplate}
                onCopyTemplateContract={props.onCopyTemplateContract}
                onAddTeamCanvas={addTeamCanvas}
                onAttachSkillToTemplate={attachSkillToTemplate}
                onRemoveSkillFromTemplate={removeSkillFromTemplate}
                onAttachTemplateToTeam={attachTemplateToTeam}
                onRemoveTemplateFromTeam={removeTemplateFromTeam}
                onDeleteTemplate={handleDeleteTemplate}
                onDeleteSkill={handleDeleteSkill}
                onDeleteTeamTemplate={handleDeleteTeamTemplate}
            />

            <TemplateDetailDrawer
                open={detailsOpen}
                template={selectedTemplate}
                onClose={() => setDetailsOpen(false)}
                onLoadTemplate={(templateSlug) => {
                    openAgentBuilder(templateSlug);
                    setDetailsOpen(false);
                }}
                onCreateFromTemplate={props.onCreateFromTemplate}
                onCopyTemplateContract={props.onCopyTemplateContract}
            />

            <Drawer
                anchor="right"
                open={agentBuilderOpen}
                onClose={() => setAgentBuilderOpen(false)}
                PaperProps={{ sx: { width: { xs: "100vw", xl: 920 } } }}
            >
                <Stack spacing={2} sx={{ p: 3 }}>
                    <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} justifyContent="space-between">
                        <div>
                            <Typography variant="h6">
                                {editingAgentTemplateSlug ? "Edit agent template" : "Add agent template"}
                            </Typography>
                            <Typography variant="body2" color="text.secondary">
                                Builder opens from library. Save template or create agent from current config.
                            </Typography>
                        </div>
                        <Stack direction="row" spacing={1}>
                            <Button onClick={() => setAgentBuilderOpen(false)}>Close</Button>
                            <Button variant="contained" onClick={saveAgentTemplate}>
                                Save template
                            </Button>
                        </Stack>
                    </Stack>
                    <TemplateBuilderView
                        form={props.form}
                        setForm={props.setForm}
                        templates={agentTemplates}
                        skills={skillCatalog}
                        templatePreview={templatePreview}
                        validationError={props.validationError}
                        validationWarnings={props.validationWarnings}
                        memoryScopeOptions={props.memoryScopeOptions}
                        outputFormatOptions={props.outputFormatOptions}
                        permissionOptions={props.permissionOptions}
                        onCreateAgent={props.onCreateAgent}
                        onImportMarkdown={props.onImportMarkdown}
                        createAgentError={props.createAgentError}
                        isCreatingAgent={props.isCreatingAgent}
                        agents={props.agents}
                        isLoadingAgents={props.isLoadingAgents}
                        agentLiveStatus={props.agentLiveStatus}
                        simulationAgentId={props.simulationAgentId}
                        isSimulatingAgent={props.isSimulatingAgent}
                        getSkillDisplayName={(slug) => skillCatalog.find((item) => item.slug === slug)?.name ?? props.getSkillDisplayName(slug)}
                        onDuplicateAgent={props.onDuplicateAgent}
                        onToggleAgent={props.onToggleAgent}
                        onOpenVersions={props.onOpenVersions}
                        onOpenTestRun={props.onOpenTestRun}
                        onSimulateAgent={props.onSimulateAgent}
                        showRegistryPanel={false}
                    />
                </Stack>
            </Drawer>

            <Drawer
                anchor="right"
                open={skillBuilderOpen}
                onClose={() => setSkillBuilderOpen(false)}
                PaperProps={{ sx: { width: { xs: "100vw", sm: 480 } } }}
            >
                <Stack spacing={1} sx={{ p: 5 }}>
                    <Stack direction={{ xs: "column", sm: "row" }} spacing={1} justifyContent="space-between">
                        <div>
                            <Typography variant="h6">
                                {editingSkillSlug ? "Edit skill" : "Add skill"}
                            </Typography>

                        </div>
                        <Stack direction="row" spacing={0.5}>
                            {!editingSkillSlug ? (
                                <Button component="label" variant="outlined" startIcon={<UploadIcon />}>
                                    Upload
                                    <input
                                        hidden
                                        type="file"
                                        accept=".md,text/markdown"
                                        onChange={(event) => {
                                            const file = event.target.files?.[0];
                                            if (file) {
                                                void handleSkillMarkdownUpload(file);
                                            }
                                            event.target.value = "";
                                        }}
                                    />
                                </Button>
                            ) : null}
                            <Button onClick={() => setSkillBuilderOpen(false)}>Close</Button>

                        </Stack>
                    </Stack>

                    <Stack spacing={2}>

                        <TextField
                            fullWidth
                            label="Name"
                            value={skillForm.name}

                            onChange={(event) => setSkillForm((current) => ({ ...current, name: event.target.value }))}
                        />

                        <TextField
                            fullWidth
                            label="Description"
                            multiline
                            minRows={4}
                            value={skillForm.description}
                            onChange={(event) => setSkillForm((current) => ({ ...current, description: event.target.value }))}
                        />

                        <TextField
                            fullWidth
                            label="Capabilities"
                            helperText="Comma-separated"
                            value={skillForm.capabilities}
                            onChange={(event) => setSkillForm((current) => ({ ...current, capabilities: event.target.value }))}
                        />
                    </Stack>
                    <Button variant="contained"   onClick={saveSkill}>
                        Save
                    </Button>
                </Stack>
            </Drawer>
        </Stack>
    );
}
