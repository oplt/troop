import { Button, Chip, Paper, Stack, Typography } from "@mui/material";
import type { ReactNode } from "react";

type CatalogCardProps = {
    title: string;
    description: string;
    /** Single meta chip (category/role) or multiple capability tags. */
    tags?: string[];
    meta?: string;
    scope?: string;
    primaryCta?: {
        label: string;
        onClick: () => void;
        disabled?: boolean;
        loadingLabel?: string;
    };
    secondaryAction?: ReactNode;
};

/**
 * Shared browse card for Skills / Marketplace capability catalogs.
 */
export function CatalogCard({
    title,
    description,
    tags = [],
    meta,
    scope,
    primaryCta,
    secondaryAction,
}: CatalogCardProps) {
    const chips = [
        ...(scope ? [scope] : []),
        ...(meta ? [meta] : []),
        ...tags,
    ].filter(Boolean);

    return (
        <Paper variant="outlined" sx={{ p: 2, height: "100%" }}>
            <Stack spacing={1} sx={{ height: "100%" }}>
                <Typography variant="subtitle1">{title}</Typography>
                {chips.length > 0 ? (
                    <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
                        {chips.map((label) => (
                            <Chip key={label} size="small" label={label} variant="outlined" />
                        ))}
                    </Stack>
                ) : null}
                <Typography variant="body2" color="text.secondary" sx={{ flex: 1 }}>
                    {description}
                </Typography>
                <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                    {primaryCta ? (
                        <Button
                            size="small"
                            variant="contained"
                            onClick={primaryCta.onClick}
                            disabled={primaryCta.disabled}
                        >
                            {primaryCta.disabled && primaryCta.loadingLabel
                                ? primaryCta.loadingLabel
                                : primaryCta.label}
                        </Button>
                    ) : null}
                    {secondaryAction}
                </Stack>
            </Stack>
        </Paper>
    );
}
