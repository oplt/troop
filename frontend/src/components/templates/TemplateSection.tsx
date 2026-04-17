import { useState } from "react";
import { Button, Stack } from "@mui/material";
import { ExpandLess as CollapseIcon, ExpandMore as ExpandIcon } from "@mui/icons-material";

import { SectionCard } from "../ui/SectionCard";

type TemplateSectionProps = {
    title: React.ReactNode;
    description?: React.ReactNode;
    action?: React.ReactNode;
    children: React.ReactNode;
    defaultExpanded?: boolean;
};

export function TemplateSection({
    title,
    description,
    action,
    children,
    defaultExpanded = true,
}: TemplateSectionProps) {
    const [expanded, setExpanded] = useState(defaultExpanded);

    return (
        <SectionCard
            title={title}
            description={description}
            action={(
                <Stack direction="row" spacing={1} alignItems="center">
                    {action}
                    <Button
                        size="small"
                        variant="text"
                        endIcon={expanded ? <CollapseIcon /> : <ExpandIcon />}
                        onClick={() => setExpanded((current) => !current)}
                    >
                        {expanded ? "Collapse" : "Expand"}
                    </Button>
                </Stack>
            )}
        >
            {expanded ? children : null}
        </SectionCard>
    );
}
