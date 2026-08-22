import { Box, Tab, Tabs } from "@mui/material";
import type { ReactNode } from "react";

import {
    AI_WORKSPACE_SECTIONS,
    defaultSectionForWorkspace,
    workspaceForSection,
    type AiSection,
    type AiWorkspace,
} from "./formUtils";

const SECTION_LABELS: Record<AiSection, string> = {
    prompts: "Prompt",
    versions: "Versions",
    playground: "Playground",
    datasets: "Evaluations",
    reviews: "Reviews",
    documents: "Documents",
    retrieval: "Retrieval inspector",
};

type AiSectionPanelProps = {
    activeSection: AiSection;
    value: AiSection;
    children: ReactNode;
};

export function AiSectionPanel({ activeSection, value, children }: AiSectionPanelProps) {
    const panelId = `ai-panel-${value}`;
    const tabId = `ai-tab-${value}`;
    return (
        <Box
            role="tabpanel"
            hidden={activeSection !== value}
            id={panelId}
            aria-labelledby={tabId}
            sx={{ pt: 2 }}
        >
            {activeSection === value ? children : null}
        </Box>
    );
}

type AiStudioTabsProps = {
    activeSection: AiSection;
    onSectionChange: (value: AiSection) => void;
    children: ReactNode;
};

export function AiStudioTabs({ activeSection, onSectionChange, children }: AiStudioTabsProps) {
    const activeWorkspace = workspaceForSection(activeSection);
    return (
        <Box sx={{ mt: 2 }}>
            <Tabs
                value={activeWorkspace}
                onChange={(_, value: AiWorkspace) => onSectionChange(defaultSectionForWorkspace(value))}
                variant="scrollable"
                scrollButtons="auto"
                allowScrollButtonsMobile
                aria-label="AI Studio workspaces"
                sx={{ borderBottom: 1, borderColor: "divider" }}
            >
                <Tab value="build" label="Build" />
                <Tab value="test" label="Test" />
                <Tab value="knowledge" label="Knowledge" />
            </Tabs>
            <Tabs
                value={activeSection}
                onChange={(_, value: AiSection) => onSectionChange(value)}
                variant="scrollable"
                scrollButtons="auto"
                allowScrollButtonsMobile
                aria-label={`${activeWorkspace} tools`}
                sx={{ borderBottom: 1, borderColor: "divider" }}
            >
                {AI_WORKSPACE_SECTIONS[activeWorkspace].map((section) => (
                    <Tab
                        key={section}
                        id={`ai-tab-${section}`}
                        aria-controls={`ai-panel-${section}`}
                        value={section}
                        label={SECTION_LABELS[section]}
                    />
                ))}
            </Tabs>
            {children}
        </Box>
    );
}
