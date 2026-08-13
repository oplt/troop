import { Stack, type SxProps, type Theme } from "@mui/material";

type FilterToolbarProps = {
    children: React.ReactNode;
    /** Optional trailing actions (primary button, overflow). */
    actions?: React.ReactNode;
    sx?: SxProps<Theme>;
};

/**
 * Standard filter/search row under PageHeader.
 * Hairline surface — not a nested card.
 */
export function FilterToolbar({ children, actions, sx }: FilterToolbarProps) {
    return (
        <Stack
            direction={{ xs: "column", md: "row" }}
            spacing={1.5}
            alignItems={{ xs: "stretch", md: "center" }}
            justifyContent="space-between"
            sx={[
                {
                    py: 1.5,
                    borderBottom: "1px solid",
                    borderColor: "divider",
                },
                ...(Array.isArray(sx) ? sx : sx ? [sx] : []),
            ]}
        >
            <Stack
                direction={{ xs: "column", sm: "row" }}
                spacing={1.5}
                alignItems={{ xs: "stretch", sm: "center" }}
                useFlexGap
                flexWrap="wrap"
                sx={{ flex: 1, minWidth: 0 }}
            >
                {children}
            </Stack>
            {actions ? (
                <Stack direction="row" spacing={1} alignItems="center" sx={{ flexShrink: 0 }}>
                    {actions}
                </Stack>
            ) : null}
        </Stack>
    );
}
