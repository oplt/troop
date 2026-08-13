import { Box, Container, Stack, type Breakpoint, type SxProps, type Theme } from "@mui/material";

export type PageShellVariant = "browse" | "form" | "inspector";

const VARIANT_MAX_WIDTH: Record<PageShellVariant, Breakpoint | false> = {
    browse: "xl",
    form: "md",
    inspector: false,
};

type PageShellProps = {
    children: React.ReactNode;
    /** @deprecated Prefer `variant`. Kept for call-site compatibility. */
    maxWidth?: Breakpoint | false;
    /**
     * browse = list/catalog (xl), form = settings/forms (md),
     * inspector = fluid full-bleed tool surfaces.
     */
    variant?: PageShellVariant;
    /** Fade/slide page content in (0.33s product motion). Default true. */
    animate?: boolean;
    sx?: SxProps<Theme>;
};

export function PageShell({
    children,
    maxWidth,
    variant = "browse",
    animate = true,
    sx,
}: PageShellProps) {
    const resolvedMaxWidth = maxWidth ?? VARIANT_MAX_WIDTH[variant];
    return (
        <Box
            className={animate ? "troop-page-enter" : undefined}
            sx={[
                {
                    position: "relative",
                    px: { xs: 2, md: 3 },
                    py: { xs: 3, md: 4 },
                },
                ...(Array.isArray(sx) ? sx : sx ? [sx] : []),
            ]}
        >
            <Container
                maxWidth={resolvedMaxWidth}
                sx={{
                    px: "0 !important",
                    ...(resolvedMaxWidth === false ? { maxWidth: "100% !important" } : null),
                }}
            >
                <Stack spacing={{ xs: 3, md: 4 }}>{children}</Stack>
            </Container>
        </Box>
    );
}
