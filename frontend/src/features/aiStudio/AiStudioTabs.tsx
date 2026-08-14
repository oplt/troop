import { Box, Tab, Tabs } from "@mui/material";
import type { ReactNode } from "react";

import type { AiSection } from "./formUtils";

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
    return (
        <Box sx={{ mt: 2 }}>
            <Tabs
                value={activeSection}
                onChange={(_, value: AiSection) => onSectionChange(value)}
                variant="scrollable"
                scrollButtons="auto"
                allowScrollButtonsMobile
                aria-label="AI Studio sections"
                sx={{ borderBottom: 1, borderColor: "divider" }}
            >
                <Tab id="ai-tab-prompts" aria-controls="ai-panel-prompts" value="prompts" label="Prompt" />
                <Tab id="ai-tab-playground" aria-controls="ai-panel-playground" value="playground" label="Playground" />
                <Tab id="ai-tab-versions" aria-controls="ai-panel-versions" value="versions" label="Versions" />
                <Tab id="ai-tab-documents" aria-controls="ai-panel-documents" value="documents" label="Retrieval" />
                <Tab id="ai-tab-reviews" aria-controls="ai-panel-reviews" value="reviews" label="Reviews" />
                <Tab id="ai-tab-datasets" aria-controls="ai-panel-datasets" value="datasets" label="Datasets" />
            </Tabs>
            {children}
        </Box>
    );
}
