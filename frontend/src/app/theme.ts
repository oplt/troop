import { alpha, createTheme, type PaletteMode } from "@mui/material/styles";

function buildTheme(mode: PaletteMode) {
    const isDark = mode === "dark";

    const ink = "#0c0a09";
    const warmInk = "#292524";
    const body = "#4e4e4e";
    const canvas = "#f5f5f5";
    const canvasSoft = "#fafafa";
    const hairline = "#e7e5e4";
    const hairlineStrong = "#d6d3d1";
    const surfaceDark = "#0c0a09";
    const darkElevated = "#1c1917";
    const darkBorder = "rgba(255,255,255,0.11)";
    const mint = "#a7e5d3";
    const peach = "#f4c5a8";
    const sky = "#a8c8e8";

    const theme = createTheme({
        palette: {
            mode,
            primary: {
                main: isDark ? canvas : warmInk,
                light: isDark ? "#ffffff" : "#44403c",
                dark: isDark ? hairline : ink,
                contrastText: isDark ? ink : "#ffffff",
            },
            secondary: {
                main: isDark ? sky : "#5f7f91",
                light: sky,
                dark: "#334e5c",
                contrastText: isDark ? ink : "#ffffff",
            },
            success: {
                main: "#16a34a",
            },
            warning: {
                main: "#b7791f",
            },
            error: {
                main: "#dc2626",
            },
            info: {
                main: isDark ? mint : "#3f7f70",
            },
            background: {
                default: isDark ? surfaceDark : canvas,
                paper: isDark ? darkElevated : "#ffffff",
            },
            text: {
                primary: isDark ? "#ffffff" : ink,
                secondary: isDark ? "rgba(255,255,255,0.66)" : body,
            },
            divider: isDark ? darkBorder : hairline,
        },
        shape: {
            borderRadius: 8,
        },
        typography: {
            fontFamily:
                "'Manrope', ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
            h1: {
                fontFamily: "'Times New Roman', Georgia, serif",
                fontSize: "clamp(2.75rem, 6vw, 5.5rem)",
                fontWeight: 300,
                letterSpacing: 0,
                lineHeight: 1.02,
            },
            h2: {
                fontFamily: "'Times New Roman', Georgia, serif",
                fontSize: "clamp(2.25rem, 4.2vw, 4rem)",
                fontWeight: 300,
                letterSpacing: 0,
                lineHeight: 1.05,
            },
            h3: {
                fontFamily: "'Times New Roman', Georgia, serif",
                fontSize: "clamp(2rem, 3vw, 3rem)",
                fontWeight: 300,
                letterSpacing: 0,
                lineHeight: 1.1,
            },
            h4: {
                fontFamily: "'Times New Roman', Georgia, serif",
                fontSize: "2rem",
                fontWeight: 300,
                letterSpacing: 0,
                lineHeight: 1.15,
            },
            h5: {
                fontSize: "1.25rem",
                fontWeight: 500,
                letterSpacing: 0,
                lineHeight: 1.35,
            },
            h6: {
                fontSize: "1.05rem",
                fontWeight: 600,
                letterSpacing: 0,
                lineHeight: 1.35,
            },
            subtitle1: {
                fontSize: "1rem",
                fontWeight: 600,
            },
            subtitle2: {
                fontSize: "0.875rem",
                fontWeight: 600,
            },
            body1: {
                fontSize: "1rem",
                lineHeight: 1.5,
                fontWeight: 400,
            },
            body2: {
                fontSize: "0.92rem",
                lineHeight: 1.5,
                fontWeight: 400,
            },
            button: {
                fontSize: "0.92rem",
                fontWeight: 600,
                textTransform: "none",
                letterSpacing: 0,
            },
            overline: {
                fontSize: "0.72rem",
                fontWeight: 700,
                letterSpacing: "0.08em",
                textTransform: "uppercase",
            },
            caption: {
                fontSize: "0.82rem",
                lineHeight: 1.5,
                fontWeight: 400,
            },
        },
    });

    return createTheme(theme, {
        components: {
            MuiCssBaseline: {
                styleOverrides: {
                    ":root": {
                        colorScheme: mode,
                    },
                    "*, *::before, *::after": {
                        boxSizing: "border-box",
                    },
                    html: {
                        minHeight: "100%",
                    },
                    body: {
                        minHeight: "100vh",
                        margin: 0,
                        backgroundColor: theme.palette.background.default,
                        color: theme.palette.text.primary,
                        textRendering: "optimizeLegibility",
                        WebkitFontSmoothing: "antialiased",
                        MozOsxFontSmoothing: "grayscale",
                    },
                    "#root": {
                        minHeight: "100vh",
                    },
                    "::selection": {
                        backgroundColor: alpha(peach, 0.55),
                    },
                },
            },
            MuiAppBar: {
                styleOverrides: {
                    root: {
                        backgroundImage: "none",
                        borderBottom: `1px solid ${theme.palette.divider}`,
                        boxShadow: "none",
                    },
                },
            },
            MuiPaper: {
                styleOverrides: {
                    root: {
                        backgroundImage: "none",
                        borderRadius: 8,
                    },
                    rounded: {
                        borderRadius: 8,
                    },
                },
            },
            MuiCard: {
                defaultProps: {
                    elevation: 0,
                },
                styleOverrides: {
                    root: {
                        borderRadius: 8,
                        border: `1px solid ${theme.palette.divider}`,
                        backgroundColor: theme.palette.background.paper,
                        boxShadow: isDark
                            ? "0 18px 36px rgba(0,0,0,0.24)"
                            : "0 18px 48px rgba(41,37,36,0.06)",
                    },
                },
            },
            MuiButton: {
                defaultProps: {
                    disableElevation: true,
                },
                styleOverrides: {
                    root: {
                        minHeight: 40,
                        paddingInline: 18,
                        borderRadius: 999,
                    },
                    contained: {
                        backgroundColor: theme.palette.primary.main,
                        color: theme.palette.primary.contrastText,
                        "&:hover": {
                            backgroundColor: theme.palette.primary.dark,
                        },
                    },
                    outlined: {
                        borderColor: isDark ? darkBorder : hairlineStrong,
                        backgroundColor: "transparent",
                    },
                    text: {
                        color: theme.palette.text.primary,
                    },
                    sizeSmall: {
                        minHeight: 34,
                        paddingInline: 14,
                    },
                },
            },
            MuiChip: {
                styleOverrides: {
                    root: {
                        borderRadius: 999,
                        fontWeight: 600,
                    },
                    outlined: {
                        borderColor: alpha(theme.palette.text.primary, isDark ? 0.14 : 0.12),
                    },
                },
            },
            MuiOutlinedInput: {
                styleOverrides: {
                    root: {
                        borderRadius: 8,
                        backgroundColor: isDark ? alpha("#ffffff", 0.03) : canvasSoft,
                        transition: theme.transitions.create(["box-shadow", "background-color"], {
                            duration: theme.transitions.duration.shortest,
                        }),
                        "&:hover .MuiOutlinedInput-notchedOutline": {
                            borderColor: isDark ? alpha("#ffffff", 0.24) : hairlineStrong,
                        },
                        "&.Mui-focused": {
                            boxShadow: `0 0 0 4px ${alpha(isDark ? sky : mint, 0.26)}`,
                        },
                    },
                    notchedOutline: {
                        borderColor: theme.palette.divider,
                    },
                    input: {
                        paddingBlock: 12,
                    },
                },
            },
            MuiInputLabel: {
                styleOverrides: {
                    root: {
                        fontWeight: 500,
                    },
                },
            },
            MuiAlert: {
                styleOverrides: {
                    root: {
                        borderRadius: 8,
                    },
                    standardInfo: {
                        backgroundColor: alpha(sky, isDark ? 0.18 : 0.2),
                    },
                },
            },
            MuiAvatar: {
                styleOverrides: {
                    root: {
                        fontWeight: 700,
                    },
                },
            },
            MuiDrawer: {
                styleOverrides: {
                    paper: {
                        borderRadius: 0,
                        borderRight: `1px solid ${theme.palette.divider}`,
                        backgroundColor: theme.palette.background.default,
                    },
                },
            },
            MuiListItemButton: {
                styleOverrides: {
                    root: {
                        borderRadius: 8,
                        minHeight: 46,
                        "&.Mui-selected": {
                            backgroundColor: alpha(isDark ? "#ffffff" : warmInk, isDark ? 0.1 : 0.08),
                            color: theme.palette.text.primary,
                            "& .MuiListItemIcon-root": {
                                color: theme.palette.text.primary,
                            },
                        },
                        "&:hover": {
                            backgroundColor: alpha(isDark ? "#ffffff" : warmInk, isDark ? 0.07 : 0.05),
                        },
                    },
                },
            },
            MuiTableCell: {
                styleOverrides: {
                    head: {
                        fontWeight: 700,
                        color: theme.palette.text.secondary,
                        backgroundColor: alpha(isDark ? "#ffffff" : warmInk, isDark ? 0.06 : 0.035),
                    },
                },
            },
            MuiTooltip: {
                styleOverrides: {
                    tooltip: {
                        borderRadius: 6,
                        backgroundColor: isDark ? canvasSoft : ink,
                        color: isDark ? ink : "#ffffff",
                        fontSize: "0.78rem",
                    },
                },
            },
            MuiSkeleton: {
                defaultProps: {
                    animation: "wave",
                },
                styleOverrides: {
                    rounded: {
                        borderRadius: 8,
                    },
                },
            },
            MuiLinearProgress: {
                styleOverrides: {
                    root: {
                        borderRadius: 999,
                    },
                },
            },
        },
    });
}

export const lightTheme = buildTheme("light");
export const darkTheme = buildTheme("dark");

export type ColorMode = "light" | "dark" | "system";
