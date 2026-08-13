import { Box, Stack, Typography } from "@mui/material";
import { alpha } from "@mui/material/styles";

type Highlight = {
    value: string;
    label: string;
};

type AuthMarketingPanelProps = {
    appName: string;
    /** One-sentence product value prop (not marketing fluff). */
    valueProp: string;
    eyebrow?: string;
    /** Optional secondary headline under the brand. Prefer short. */
    title?: string;
    description?: string;
    highlights?: Highlight[];
    points?: string[];
};

/**
 * Brand-first auth side panel: product name is the hero signal;
 * one value sentence + calm ops cues — not a photo hero.
 */
export function AuthMarketingPanel({
    appName,
    valueProp,
    eyebrow = "Ops workspace",
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
                        sx={{ color: "text.secondary", display: "block", mb: 1.5 }}
                    >
                        {eyebrow}
                    </Typography>
                    <Typography
                        component="h1"
                        variant="h1"
                        sx={{
                            fontFamily: (theme) => theme.typography.h1.fontFamily,
                            fontWeight: 600,
                            letterSpacing: "-0.03em",
                            mb: 1.5,
                            fontSize: { xs: "2.4rem", md: "3rem" },
                            lineHeight: 1.05,
                        }}
                    >
                        {appName}
                    </Typography>
                    <Typography
                        variant="h5"
                        component="h2"
                        sx={{ color: "text.primary", fontWeight: 500, maxWidth: 520, mb: description || title ? 1 : 0 }}
                    >
                        {valueProp}
                    </Typography>
                    {title ? (
                        <Typography variant="subtitle1" component="p" sx={{ color: "text.secondary", mt: 1, maxWidth: 560 }}>
                            {title}
                        </Typography>
                    ) : null}
                    {description ? (
                        <Typography sx={{ color: "text.secondary", mt: 1, maxWidth: 620 }}>
                            {description}
                        </Typography>
                    ) : null}
                </Box>

                {highlights.length > 0 && (
                    <Box
                        sx={{
                            display: "grid",
                            gap: 2,
                            gridTemplateColumns: { xs: "1fr", sm: "repeat(3, minmax(0, 1fr))" },
                        }}
                    >
                        {highlights.map((item) => (
                            <Box
                                key={item.label}
                                sx={{
                                    p: 2,
                                    borderRadius: 1,
                                    backgroundColor: (theme) =>
                                        theme.palette.mode === "dark"
                                            ? alpha(theme.palette.common.white, 0.04)
                                            : theme.palette.grey[50],
                                }}
                            >
                                <Typography variant="h5" component="p" sx={{ fontWeight: 600 }}>
                                    {item.value}
                                </Typography>
                                <Typography sx={{ color: "text.secondary", mt: 0.5 }}>
                                    {item.label}
                                </Typography>
                            </Box>
                        ))}
                    </Box>
                )}
            </Stack>

            <Stack spacing={1.25}>
                {points.map((point) => (
                    <Box
                        key={point}
                        sx={{
                            p: 1.5,
                            borderRadius: 1,
                            backgroundColor: (theme) =>
                                theme.palette.mode === "dark"
                                    ? alpha(theme.palette.common.white, 0.04)
                                    : theme.palette.grey[50],
                        }}
                    >
                        <Typography sx={{ color: "text.secondary" }}>{point}</Typography>
                    </Box>
                ))}
            </Stack>
        </Stack>
    );
}
