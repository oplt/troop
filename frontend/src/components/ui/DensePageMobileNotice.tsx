import { Alert, Button, Stack, useMediaQuery } from "@mui/material";
import { useTheme } from "@mui/material/styles";

type DensePageMobileNoticeProps = {
    /** Short surface name, e.g. "Hierarchy builder". */
    surface: string;
};

/**
 * Mobile fallback cue for dense tool surfaces (canvas, kanban, inspector).
 * Shell keeps drawer + ≥40px targets; pages hide secondary columns where wired.
 */
export function DensePageMobileNotice({ surface }: DensePageMobileNoticeProps) {
    const theme = useTheme();
    const isMobile = useMediaQuery(theme.breakpoints.down("md"));
    if (!isMobile) {
        return null;
    }
    return (
        <Alert
            severity="info"
            role="status"
            sx={{ borderRadius: 1 }}
            action={
                <Button
                    color="inherit"
                    size="small"
                    onClick={() => {
                        // Hint only — cannot force desktop layout on a phone viewport.
                        window.scrollTo({ top: 0, behavior: "smooth" });
                    }}
                >
                    Open on desktop
                </Button>
            }
        >
            <Stack spacing={0.25}>
                <span>
                    {surface} works best on a larger screen. On mobile: use the list or primary panel;
                    secondary columns and side consoles stay hidden or open full-screen.
                </span>
            </Stack>
        </Alert>
    );
}
