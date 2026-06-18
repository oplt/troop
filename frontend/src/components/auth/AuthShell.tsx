import { Box, Container, Paper } from "@mui/material";

type AuthShellProps = {
    sideContent: React.ReactNode;
    children: React.ReactNode;
};

export function AuthShell({ sideContent, children }: AuthShellProps) {
    return (
        <Box
            sx={(theme) => ({
                minHeight: "100vh",
                display: "flex",
                alignItems: "center",
                px: { xs: 2, md: 3 },
                py: { xs: 3, md: 4 },
                backgroundColor: theme.palette.background.default,
            })}
        >
            <Container maxWidth="xl" sx={{ px: "0 !important" }}>
                <Box
                    sx={{
                        display: "grid",
                        gridTemplateColumns: { xs: "1fr", lg: "minmax(0, 1.08fr) minmax(420px, 0.92fr)" },
                        gap: { xs: 2, lg: 3 },
                        alignItems: "stretch",
                    }}
                >
                    <Paper
                        sx={(theme) => ({
                            p: { xs: 3, md: 4.5 },
                            borderRadius: 1,
                            overflow: "hidden",
                            position: "relative",
                            color: theme.palette.text.primary,
                            backgroundColor: theme.palette.mode === "dark" ? "#1E2128" : theme.palette.background.paper,
                        })}
                    >
                        <Box sx={{ position: "relative", zIndex: 1, height: "100%" }}>
                            {sideContent}
                        </Box>
                    </Paper>
                    <Paper
                        sx={{
                            p: { xs: 3, md: 4 },
                            borderRadius: 1,
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                            minHeight: { lg: 720 },
                        }}
                    >
                        <Box sx={{ width: "100%", maxWidth: 440 }}>{children}</Box>
                    </Paper>
                </Box>
            </Container>
        </Box>
    );
}
