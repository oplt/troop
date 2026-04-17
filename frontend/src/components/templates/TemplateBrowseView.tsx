import { useMemo, useState } from "react";
import { Box, Button, Stack } from "@mui/material";

import type { AgentTemplate, SkillPack } from "../../api/orchestration";
import { SkillTemplateCard } from "./SkillTemplateCard";
import { TemplateCard } from "./TemplateCard";
import { TeamTemplateCard } from "./TeamTemplateCard";
import { TemplateSection } from "./TemplateSection";
import type { StaticTeamTemplate, TemplateFilterState } from "./types";

type TemplateBrowseViewProps = {
    templates: AgentTemplate[];
    skills: SkillPack[];
    teamTemplates: StaticTeamTemplate[];
    searchQuery: string;
    filters: TemplateFilterState;
    onOpenDetails: (templateSlug: string) => void;
    onOpenAgentBuilder: (templateSlug?: string) => void;
    onOpenSkillBuilder: () => void;
    onAddSkillFromCard: (skill: SkillPack) => void;
    onEditSkill: (skill: SkillPack) => void;
    onCreateFromTemplate: (templateSlug: string) => void;
    onCopyTemplateContract: (template: AgentTemplate) => void;
    onAddTeamCanvas: () => void;
    onAttachSkillToTemplate: (templateSlug: string, skillSlug: string) => void;
    onRemoveSkillFromTemplate: (templateSlug: string, skillSlug: string) => void;
    onAttachTemplateToTeam: (teamTemplateId: string, templateSlug: string) => void;
    onRemoveTemplateFromTeam: (teamTemplateId: string, templateSlug: string) => void;
    onDeleteTemplate: (templateSlug: string) => void;
    onDeleteSkill: (skillSlug: string) => void;
    onDeleteTeamTemplate: (templateId: string) => void;
};

function matchesTemplate(template: AgentTemplate, searchQuery: string, filters: TemplateFilterState) {
    const haystack = [
        template.name,
        template.slug,
        template.role,
        template.description,
        ...template.skills,
        ...template.tags,
        ...template.allowed_tools,
        ...template.capabilities,
    ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();

    if (searchQuery && !haystack.includes(searchQuery.toLowerCase())) return false;
    if (filters.type !== "all" && filters.type !== "agent") return false;
    if (filters.roles.length > 0 && !filters.roles.includes(template.role)) return false;
    if (filters.tools.length > 0 && !filters.tools.some((tool) => template.allowed_tools.includes(tool))) return false;
    if (filters.domains.length > 0 && !filters.domains.some((item) => template.tags.includes(item))) return false;
    if (filters.outcomes.length > 0 && !filters.outcomes.some((item) => template.capabilities.includes(item))) return false;
    return true;
}

function matchesTeamTemplate(template: StaticTeamTemplate, searchQuery: string, filters: TemplateFilterState) {
    const haystack = [
        template.name,
        template.description,
        template.outcome,
        ...template.roles,
        ...template.tools,
    ]
        .join(" ")
        .toLowerCase();
    if (searchQuery && !haystack.includes(searchQuery.toLowerCase())) return false;
    if (filters.type !== "all" && filters.type !== "team") return false;
    if (filters.roles.length > 0 && !filters.roles.some((item) => template.roles.includes(item))) return false;
    if (filters.tools.length > 0 && !filters.tools.some((item) => template.tools.includes(item))) return false;
    if (filters.outcomes.length > 0 && !filters.outcomes.includes(template.outcome)) return false;
    if (filters.autonomy.length > 0 && !filters.autonomy.includes(template.autonomy)) return false;
    if (filters.visibility.length > 0 && !filters.visibility.includes(template.visibility)) return false;
    return true;
}

function matchesSkillTemplate(skill: SkillPack, searchQuery: string, filters: TemplateFilterState) {
    const haystack = [
        skill.name,
        skill.slug,
        skill.description,
        ...skill.capabilities,
        ...skill.tags,
        ...skill.allowed_tools,
    ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
    if (searchQuery && !haystack.includes(searchQuery.toLowerCase())) return false;
    if (filters.type !== "all" && filters.type !== "skill") return false;
    if (filters.tools.length > 0 && !filters.tools.some((item) => skill.allowed_tools.includes(item))) return false;
    if (filters.domains.length > 0 && !filters.domains.some((item) => skill.tags.includes(item))) return false;
    if (filters.outcomes.length > 0 && !filters.outcomes.some((item) => skill.capabilities.includes(item))) return false;
    return true;
}

export function TemplateBrowseView({
    templates,
    skills,
    teamTemplates,
    searchQuery,
    filters,
    onOpenDetails,
    onOpenAgentBuilder,
    onOpenSkillBuilder,
    onAddSkillFromCard,
    onEditSkill,
    onCreateFromTemplate,
    onCopyTemplateContract,
    onAddTeamCanvas,
    onAttachSkillToTemplate,
    onRemoveSkillFromTemplate,
    onAttachTemplateToTeam,
    onRemoveTemplateFromTeam,
    onDeleteTemplate,
    onDeleteSkill,
    onDeleteTeamTemplate,
}: TemplateBrowseViewProps) {
    const [activeDrag, setActiveDrag] = useState<{ kind: "skill" | "agent-template"; slug: string } | null>(null);

    const filteredTemplates = useMemo(
        () =>
            templates
                .filter((template) => matchesTemplate(template, searchQuery, filters)),
        [filters, searchQuery, templates],
    );
    const filteredTeamTemplates = useMemo(
        () =>
            teamTemplates
                .filter((template) => matchesTeamTemplate(template, searchQuery, filters)),
        [filters, searchQuery, teamTemplates],
    );
    const filteredSkillTemplates = useMemo(
        () =>
            skills
                .filter((skill) => matchesSkillTemplate(skill, searchQuery, filters)),
        [filters, searchQuery, skills],
    );


    return (
        <Stack spacing={2}>


            <TemplateSection
                title="Agent templates"
                description="Single-agent profiles for manager, specialist, reviewer flows."
                action={<Button size="small" variant="contained" onClick={() => onOpenAgentBuilder()}>Add</Button>}
            >
                <Box sx={{ display: "grid", gap: 1.25, gridTemplateColumns: { xs: "1fr", sm: "repeat(2, minmax(0, 1fr))", lg: "repeat(3, minmax(0, 1fr))", xl: "repeat(4, minmax(0, 1fr))" } }}>
                    {filteredTemplates.map((template) => (
                        <TemplateCard
                            key={`agent-${template.slug}`}
                            template={template}
                            onOpenDetails={onOpenDetails}
                            onLoadTemplate={onOpenAgentBuilder}
                            onCreateFromTemplate={onCreateFromTemplate}
                            onCopyTemplateContract={onCopyTemplateContract}
                            onRemoveSkill={onRemoveSkillFromTemplate}
                            onDragStart={(templateSlug) => setActiveDrag({ kind: "agent-template", slug: templateSlug })}
                            onDragEnd={() => setActiveDrag(null)}
                            onDropSkill={onAttachSkillToTemplate}
                            activeSkillSlug={activeDrag?.kind === "skill" ? activeDrag.slug : null}
                            onRemove={onDeleteTemplate}
                        />
                    ))}
                </Box>
            </TemplateSection>



            <TemplateSection
                title="Team templates"
                description="Presentational multi-agent stacks. Seed builder from these patterns."
                action={<Button size="small" variant="contained" onClick={onAddTeamCanvas}>Add</Button>}
            >
                <Box sx={{ display: "grid", gap: 1.25, gridTemplateColumns: { xs: "1fr", sm: "repeat(2, minmax(0, 1fr))", lg: "repeat(3, minmax(0, 1fr))", xl: "repeat(4, minmax(0, 1fr))" } }}>
                    {filteredTeamTemplates.map((template) => (
                        <Box key={template.id} sx={{ display: "contents" }}>
                            <TeamTemplateCard
                                template={template}
                                agentTemplates={template.agent_template_slugs.map((slug) => ({
                                    slug,
                                    name: templates.find((item) => item.slug === slug)?.name ?? slug,
                                }))}
                                onDragEnd={() => setActiveDrag(null)}
                                onDropAgentTemplate={onAttachTemplateToTeam}
                                onRemoveAgentTemplate={onRemoveTemplateFromTeam}
                                activeAgentTemplateSlug={activeDrag?.kind === "agent-template" ? activeDrag.slug : null}
                                onRemove={() => onDeleteTeamTemplate(template.id)}
                            />
                        </Box>
                    ))}
                </Box>
            </TemplateSection>

            <TemplateSection
                title="Skil templates"
                description="Reusable skill packs for capability-first setup."
                action={<Button size="small" variant="contained" onClick={onOpenSkillBuilder}>Add</Button>}
            >
                <Box sx={{ display: "grid", gap: 1.25, gridTemplateColumns: { xs: "1fr", sm: "repeat(2, minmax(0, 1fr))", lg: "repeat(3, minmax(0, 1fr))", xl: "repeat(4, minmax(0, 1fr))" } }}>
                    {filteredSkillTemplates.map((skill) => (
                        <SkillTemplateCard
                            key={skill.slug}
                            skill={skill}
                            onAdd={onAddSkillFromCard}
                            onEdit={onEditSkill}
                            onDragStart={(skillSlug) => setActiveDrag({ kind: "skill", slug: skillSlug })}
                            onDragEnd={() => setActiveDrag(null)}
                            onRemove={() => onDeleteSkill(skill.slug)}
                        />
                    ))}
                </Box>
            </TemplateSection>
        </Stack>
    );
}
