import { useId, useState } from "react";
import { Button, Chip, Collapse, Stack, type SxProps, type Theme } from "@mui/material";
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
    sx?: SxProps<Theme>;
};

export function CollapsibleSectionCard({
    title,
    description,
    info,
    count,
    action,
    defaultExpanded = false,
    children,
    sx,
}: CollapsibleSectionCardProps) {
    const [expanded, setExpanded] = useState(defaultExpanded);
    const sectionId = useId();
    return (
        <SectionCard
            sx={sx}
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
                        aria-expanded={expanded}
                        aria-controls={sectionId}
                        endIcon={expanded ? <CollapseIcon /> : <ExpandMoreIcon />}
                        onClick={() => setExpanded((current) => !current)}
                    >
                        {expanded ? "Collapse" : "Expand"}
                    </Button>
                </Stack>
            }
        >
            <Collapse id={sectionId} in={expanded} mountOnEnter unmountOnExit timeout="auto">
                {children}
            </Collapse>
        </SectionCard>
    );
}
