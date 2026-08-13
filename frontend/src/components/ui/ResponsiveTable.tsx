import { Box, Paper, Stack, Typography } from "@mui/material";

type ResponsiveTableProps = {
    /** Desktop table (hidden on xs). */
    table: React.ReactNode;
    /** Mobile card list (shown on xs only). */
    cards: React.ReactNode;
    empty?: React.ReactNode;
    isEmpty?: boolean;
};

/**
 * Desktop table + xs card collapse for dense list pages.
 */
export function ResponsiveTable({ table, cards, empty, isEmpty }: ResponsiveTableProps) {
    if (isEmpty) {
        return <>{empty}</>;
    }
    return (
        <>
            <Box sx={{ display: { xs: "none", md: "block" }, overflowX: "auto" }}>{table}</Box>
            <Stack spacing={1} sx={{ display: { xs: "flex", md: "none" } }}>
                {cards}
            </Stack>
        </>
    );
}

type ResponsiveRowCardProps = {
    title: React.ReactNode;
    meta?: React.ReactNode;
    actions?: React.ReactNode;
    children?: React.ReactNode;
};

export function ResponsiveRowCard({ title, meta, actions, children }: ResponsiveRowCardProps) {
    return (
        <Paper variant="outlined" sx={{ p: 1.5, borderRadius: 1 }}>
            <Stack spacing={1}>
                <Stack direction="row" justifyContent="space-between" alignItems="flex-start" gap={1}>
                    <Box sx={{ minWidth: 0 }}>
                        <Typography variant="subtitle2" noWrap>
                            {title}
                        </Typography>
                        {meta ? (
                            <Typography variant="caption" color="text.secondary" component="div">
                                {meta}
                            </Typography>
                        ) : null}
                    </Box>
                    {actions}
                </Stack>
                {children}
            </Stack>
        </Paper>
    );
}
