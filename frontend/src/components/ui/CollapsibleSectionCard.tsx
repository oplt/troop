import { useState } from "react";
import { Button, Chip, Collapse, Stack } from "@mui/material";
import { ExpandLess as CollapseIcon, ExpandMore as ExpandMoreIcon } from "@mui/icons-material";

import { SectionCard } from "./SectionCard";

type CollapsibleSectionCardProps = {
    title: React.ReactNode;
    description?: React.ReactNode;
    info?: React.ReactNode;
    count?: number;
    action?: React.ReactNode;
    defaultExpanded?: boolean;
    children: React.ReactNode;
};

export function CollapsibleSectionCard({
    title,
    description,
    info,
    count,
    action,
    defaultExpanded = false,
    children,
}: CollapsibleSectionCardProps) {
    const [expanded, setExpanded] = useState(defaultExpanded);
    return (
        <SectionCard
            title={
                <Stack direction="row" spacing={1} alignItems="center">
                    <span>{title}</span>
                    {typeof count === "number" && <Chip size="small" variant="outlined" label={count} />}
                </Stack>
            }
            description={description}
            info={info}
            action={
                <Stack direction="row" spacing={1} alignItems="center">
                    {action}
                    <Button
                        size="small"
                        variant="text"
                        endIcon={expanded ? <CollapseIcon /> : <ExpandMoreIcon />}
                        onClick={() => setExpanded((current) => !current)}
                    >
                        {expanded ? "Collapse" : "Expand"}
                    </Button>
                </Stack>
            }
        >
            <Collapse in={expanded} mountOnEnter unmountOnExit timeout="auto">
                {children}
            </Collapse>
        </SectionCard>
    );
}
