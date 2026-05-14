import { Box, Stack, Typography } from "@mui/material";
import { alpha } from "@mui/material/styles";

type Highlight = {
    value: string;
    label: string;
};

type AuthMarketingPanelProps = {
    appName: string;
    eyebrow: string;
    title: string;
    description: string;
    highlights?: Highlight[];
    points?: string[];
};

export function AuthMarketingPanel({
    appName,
    eyebrow,
    title,
    description,
    highlights = [],
    points = [],
}: AuthMarketingPanelProps) {
    return (
        <Stack justifyContent="space-between" spacing={4} sx={{ height: "100%" }}>
            <Stack spacing={3}>
                <Box>
                    <Typography
                        variant="overline"
                        sx={(theme) => ({ color: theme.palette.text.secondary, display: "block", mb: 1 })}
                    >
                        {eyebrow}
                    </Typography>
                    <Typography variant="h3" sx={{ mb: 1.25 }}>
                        {title}
                    </Typography>
                    <Typography sx={{ color: "text.secondary", maxWidth: 620 }}>
                        {description}
                    </Typography>
                </Box>

                {highlights.length > 0 && (
                    <Box
                        sx={{
                            display: "grid",
                            gap: 1.25,
                            gridTemplateColumns: { xs: "1fr", sm: "repeat(3, minmax(0, 1fr))" },
                        }}
                    >
                        {highlights.map((item) => (
                            <Box
                                key={item.label}
                                sx={{
                                    p: 2,
                                    borderRadius: 2,
                                    backgroundColor: (theme) => alpha(theme.palette.text.primary, theme.palette.mode === "dark" ? 0.08 : 0.035),
                                    border: (theme) => `1px solid ${theme.palette.divider}`,
                                }}
                            >
                                <Typography variant="h5">{item.value}</Typography>
                                <Typography sx={{ color: "text.secondary", mt: 0.5 }}>
                                    {item.label}
                                </Typography>
                            </Box>
                        ))}
                    </Box>
                )}
            </Stack>

            <Stack spacing={1.25}>
                <Typography variant="subtitle2" sx={{ color: "text.primary" }}>
                    {appName}
                </Typography>
                {points.map((point) => (
                    <Box
                        key={point}
                        sx={{
                            p: 1.5,
                            borderRadius: 2,
                            backgroundColor: (theme) => alpha(theme.palette.text.primary, theme.palette.mode === "dark" ? 0.06 : 0.03),
                            border: (theme) => `1px solid ${theme.palette.divider}`,
                        }}
                    >
                        <Typography sx={{ color: "text.secondary" }}>{point}</Typography>
                    </Box>
                ))}
            </Stack>
        </Stack>
    );
}
