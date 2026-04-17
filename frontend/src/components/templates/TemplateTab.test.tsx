import { useState } from "react";
import { fireEvent, render, screen, within } from "@testing-library/react";

import type { AgentTemplate, SkillPack } from "../../api/orchestration";
import { TemplateTab } from "./TemplateTab";
import { EMPTY_TEMPLATE_BUILDER_FORM } from "./templateBuilderState";
import type { TemplateBuilderFormState, TemplateTabProps } from "./types";

class DataTransferMock {
    effectAllowed = "";
    dropEffect = "";
    private readonly store = new Map<string, string>();

    setData(type: string, value: string) {
        this.store.set(type, value);
    }

    getData(type: string) {
        return this.store.get(type) ?? "";
    }
}

const agentTemplate: AgentTemplate = {
    slug: "reviewer-template",
    name: "Reviewer Template",
    description: "Checks changes before merge.",
    role: "reviewer",
    parent_template_slug: null,
    system_prompt: "",
    mission_markdown: "",
    rules_markdown: "",
    output_contract_markdown: "",
    capabilities: ["Review PRs"],
    allowed_tools: ["repo_search"],
    tags: ["quality"],
    skills: [],
    model_policy: {},
    budget: {},
    memory_policy: {},
    output_schema: {},
    metadata: {},
};

const skill: SkillPack = {
    slug: "review-skill",
    name: "Review skill",
    description: "Structured review capability.",
    capabilities: ["Review code"],
    allowed_tools: [],
    rules_markdown: "",
    tags: ["quality"],
};

function TestHarness(overrides: Partial<TemplateTabProps> = {}) {
    const [form, setForm] = useState<TemplateBuilderFormState>(EMPTY_TEMPLATE_BUILDER_FORM);

    return (
        <TemplateTab
            agents={[]}
            templates={[agentTemplate]}
            skills={[skill]}
            runs={[]}
            isLoadingAgents={false}
            form={form}
            setForm={setForm}
            validationError={null}
            validationWarnings={[]}
            agentLiveStatus={new Map()}
            memoryScopeOptions={["project-only"]}
            outputFormatOptions={["json"]}
            permissionOptions={["read-only"]}
            isCreatingAgent={false}
            createAgentError={null}
            isCreatingFromTemplate={false}
            isSimulatingAgent={false}
            simulationAgentId={null}
            getSkillDisplayName={(slug) => slug}
            onCopyTemplateContract={vi.fn()}
            onCreateFromTemplate={vi.fn()}
            onCreateAgent={vi.fn()}
            onResetBuilder={vi.fn()}
            onDuplicateAgent={vi.fn()}
            onToggleAgent={vi.fn()}
            onOpenVersions={vi.fn()}
            onOpenTestRun={vi.fn()}
            onSimulateAgent={vi.fn()}
            onImportMarkdown={vi.fn()}
            {...overrides}
        />
    );
}

describe("TemplateTab", () => {
    it("shows browse content by default and opens agent and skill builders from library cards", async () => {
        render(<TestHarness />);

        expect(screen.queryByRole("tab", { name: "Browse" })).not.toBeInTheDocument();
        expect(screen.queryByRole("tab", { name: "Builder" })).not.toBeInTheDocument();
        expect(screen.queryByRole("tab", { name: "My Templates" })).not.toBeInTheDocument();

        const templateCard = screen.getByText("Reviewer Template").closest(".MuiPaper-root");
        const skillCard = screen.getByText("Review skill").closest(".MuiPaper-root");

        expect(templateCard).not.toBeNull();
        expect(skillCard).not.toBeNull();

        fireEvent.click(within(templateCard as HTMLElement).getByRole("button", { name: "Edit" }));
        expect(await screen.findByText("Edit agent template")).toBeInTheDocument();

        fireEvent.click(screen.getByRole("button", { name: "Close" }));
        fireEvent.click(within(skillCard as HTMLElement).getByRole("button", { name: "Edit" }));
        expect(await screen.findByText("Edit skill")).toBeInTheDocument();
    });

    it("drops skills onto agent templates and agent templates onto team templates", () => {
        render(<TestHarness />);

        const skillCard = screen.getByText("Review skill").closest(".MuiPaper-root");
        const templateCard = screen.getByText("Reviewer Template").closest(".MuiPaper-root");
        const teamCard = screen.getByText("Feature Squad").closest(".MuiPaper-root");

        expect(skillCard).not.toBeNull();
        expect(templateCard).not.toBeNull();
        expect(teamCard).not.toBeNull();

        const skillTransfer = new DataTransferMock();
        fireEvent.dragStart(skillCard as HTMLElement, { dataTransfer: skillTransfer });
        fireEvent.dragOver(templateCard as HTMLElement, { dataTransfer: new DataTransferMock() });
        fireEvent.drop(templateCard as HTMLElement, { dataTransfer: new DataTransferMock() });

        expect(within(templateCard as HTMLElement).getByText("review-skill")).toBeInTheDocument();

        const templateTransfer = new DataTransferMock();
        fireEvent.dragStart(templateCard as HTMLElement, { dataTransfer: templateTransfer });
        fireEvent.dragOver(teamCard as HTMLElement, { dataTransfer: new DataTransferMock() });
        fireEvent.drop(teamCard as HTMLElement, { dataTransfer: new DataTransferMock() });

        expect(within(teamCard as HTMLElement).getByText("Reviewer Template")).toBeInTheDocument();
    });

    it("adds empty team canvas from team templates section", () => {
        render(<TestHarness />);

        const teamSection = screen.getByText("Team templates").closest(".MuiPaper-root");
        expect(teamSection).not.toBeNull();

        fireEvent.click(within(teamSection as HTMLElement).getByRole("button", { name: "Add" }));

        expect(screen.getByText(/Empty team canvas/i)).toBeInTheDocument();
    });

    it("uploads SKILL.md into skill builder form", async () => {
        render(<TestHarness />);

        const skillSection = screen.getByText("Skil templates").closest(".MuiPaper-root");
        expect(skillSection).not.toBeNull();

        fireEvent.click(within(skillSection as HTMLElement).getAllByRole("button", { name: "Add" })[0]);

        const uploadButton = await screen.findByRole("button", { name: "Upload SKILL.md" });
        const fileInput = uploadButton.querySelector('input[type="file"]');
        expect(fileInput).not.toBeNull();

        const file = new File([
            `---
name: repo-auditor
description: >
  Audit repository quality and flag risk.
---
# Repo Auditor

## Use this skill when
- Review architecture
- Flag regressions
`,
        ], "SKILL.md", { type: "text/markdown" });

        fireEvent.change(fileInput as HTMLInputElement, { target: { files: [file] } });

        expect(await screen.findByDisplayValue("repo-auditor")).toBeInTheDocument();
        expect(await screen.findByDisplayValue("Audit repository quality and flag risk.")).toBeInTheDocument();
        expect(await screen.findByDisplayValue("Review architecture, Flag regressions")).toBeInTheDocument();
    });
});
