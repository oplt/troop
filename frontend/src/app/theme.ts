import { alpha, createTheme, type PaletteMode } from "@mui/material/styles";

function buildTheme(mode: PaletteMode) {
    const isDark = mode === "dark";

    // Mistral Orange palette
    const mistralOrange = "#fa520f";
    const mistralFlame = "#fb6424";
    const blockOrange = "#ff8105";

    // Sunshine palette
    const sunshine700 = "#ffa110";
    const sunshine500 = "#ffb83e";
    const sunshine900 = "#ff8a00";

    // Surfaces
    const warmIvory = "#fffaeb";
    const cream = "#fff0c2";
    const mistralBlack = "#1f1f1f";
    const darkPaper = "#2a2020";

    const theme = createTheme({
        palette: {
            mode,
            primary: {
                main: mistralOrange,
                light: mistralFlame,
                dark: blockOrange,
                contrastText: "#ffffff",
            },
            secondary: {
                main: sunshine700,
                light: sunshine500,
                dark: sunshine900,
                contrastText: "#1f1f1f",
            },
            success: {
                main: isDark ? "#18E46A" : "#2F8F57",
            },
            warning: {
                main: sunshine700,
            },
            error: {
                main: isDark ? "#EF4444" : "#C84A37",
            },
            info: {
                main: isDark ? "#56D8F3" : "#1F7AA7",
            },
            background: {
                default: isDark ? mistralBlack : warmIvory,
                paper: isDark ? darkPaper : cream,
            },
            text: {
                primary: isDark ? "#ffffff" : "#1f1f1f",
                secondary: isDark ? "rgba(255,255,255,0.62)" : "rgba(31,31,31,0.62)",
            },
            divider: isDark ? "rgba(255,255,255,0.1)" : "rgba(250,82,15,0.15)",
        },
        shape: {
            borderRadius: 0,
        },
        typography: {
            fontFamily:
                "'Arial', ui-sans-serif, system-ui, 'Apple Color Emoji', 'Segoe UI Emoji', 'Segoe UI Symbol', 'Noto Color Emoji'",
            h1: {
                fontSize: "clamp(2rem, 5.13vw, 5.13rem)",
                fontWeight: 400,
                letterSpacing: "-2.05px",
                lineHeight: 1.0,
            },
            h2: {
                fontSize: "clamp(2rem, 3.5vw, 3.5rem)",
                fontWeight: 400,
                letterSpacing: "normal",
                lineHeight: 0.95,
            },
            h3: {
                fontSize: "clamp(2rem, 3vw, 3rem)",
                fontWeight: 400,
                letterSpacing: "normal",
                lineHeight: 0.95,
            },
            h4: {
                fontSize: "2rem",
                fontWeight: 400,
                letterSpacing: "normal",
                lineHeight: 1.15,
            },
            h5: {
                fontSize: "1.875rem",
                fontWeight: 400,
                letterSpacing: "normal",
                lineHeight: 1.2,
            },
            h6: {
                fontSize: "1.5rem",
                fontWeight: 400,
                letterSpacing: "normal",
                lineHeight: 1.33,
            },
            subtitle1: {
                fontSize: "1rem",
                fontWeight: 400,
            },
            subtitle2: {
                fontSize: "0.875rem",
                fontWeight: 400,
            },
            body1: {
                fontSize: "1rem",
                lineHeight: 1.5,
                fontWeight: 400,
            },
            body2: {
                fontSize: "0.9rem",
                lineHeight: 1.5,
                fontWeight: 400,
            },
            button: {
                fontSize: "1rem",
                fontWeight: 400,
                textTransform: "uppercase",
                letterSpacing: "0.05em",
            },
            overline: {
                fontSize: "0.72rem",
                fontWeight: 400,
                letterSpacing: "0.14em",
                textTransform: "uppercase",
            },
            caption: {
                fontSize: "0.875rem",
                lineHeight: 1.43,
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
                        scrollBehavior: "smooth",
                    },
                    body: {
                        minHeight: "100vh",
                        margin: 0,
                        backgroundColor: isDark ? mistralBlack : warmIvory,
                        color: theme.palette.text.primary,
                        textRendering: "optimizeLegibility",
                        WebkitFontSmoothing: "antialiased",
                        MozOsxFontSmoothing: "grayscale",
                    },
                    "#root": {
                        minHeight: "100vh",
                    },
                    "::selection": {
                        backgroundColor: alpha(theme.palette.primary.main, 0.22),
                    },
                },
            },
            MuiAppBar: {
                styleOverrides: {
                    root: {
                        backdropFilter: "none",
                        backgroundImage: "none",
                        borderBottom: `1px solid ${isDark ? "rgba(255,255,255,0.1)" : "rgba(250,82,15,0.15)"}`,
                    },
                },
            },
            MuiPaper: {
                styleOverrides: {
                    root: {
                        backgroundImage: "none",
                        borderRadius: 0,
                    },
                    rounded: {
                        borderRadius: 0,
                    },
                },
            },
            MuiCard: {
                defaultProps: {
                    elevation: 0,
                },
                styleOverrides: {
                    root: {
                        borderRadius: 0,
                        border: `1px solid ${isDark ? "rgba(255,255,255,0.1)" : "rgba(250,82,15,0.15)"}`,
                        backgroundColor: isDark ? alpha(darkPaper, 0.95) : cream,
                        boxShadow: isDark
                            ? "0 16px 40px rgba(0,0,0,0.4)"
                            : "rgba(127,99,21,0.12) -8px 16px 39px, rgba(127,99,21,0.1) -33px 64px 72px, rgba(127,99,21,0.06) -73px 144px 97px",
                    },
                },
            },
            MuiButton: {
                defaultProps: {
                    disableElevation: true,
                },
                styleOverrides: {
                    root: {
                        minHeight: 44,
                        paddingInline: 18,
                        borderRadius: 0,
                        fontWeight: 400,
                    },
                    contained: {
                        backgroundColor: mistralBlack,
                        color: "#ffffff",
                        "&:hover": {
                            backgroundColor: isDark ? "#3a3a3a" : "#2e2e2e",
                        },
                    },
                    outlined: {
                        borderColor: isDark ? "rgba(255,255,255,0.1)" : "rgba(250,82,15,0.15)",
                        backgroundColor: isDark ? alpha(darkPaper, 0.86) : cream,
                    },
                    text: {
                        color: theme.palette.text.primary,
                        paddingTop: "8px",
                        paddingBottom: 0,
                    },
                    sizeSmall: {
                        minHeight: 36,
                        paddingInline: 14,
                    },
                },
            },
            MuiChip: {
                styleOverrides: {
                    root: {
                        borderRadius: 0,
                        fontWeight: 400,
                    },
                    outlined: {
                        borderColor: alpha(theme.palette.text.primary, isDark ? 0.12 : 0.1),
                    },
                },
            },
            MuiOutlinedInput: {
                styleOverrides: {
                    root: {
                        borderRadius: 0,
                        backgroundColor: isDark
                            ? alpha(darkPaper, 0.18)
                            : alpha("#ffffff", 0.9),
                        transition: theme.transitions.create(["border-color", "box-shadow", "background-color"]),
                        "&:hover .MuiOutlinedInput-notchedOutline": {
                            borderColor: alpha(theme.palette.primary.main, 0.34),
                        },
                        "&.Mui-focused": {
                            boxShadow: `0 0 0 4px ${alpha(theme.palette.primary.main, 0.14)}`,
                        },
                    },
                    notchedOutline: {
                        borderColor: "hsl(240, 5.9%, 90%)",
                    },
                    input: {
                        paddingBlock: 14,
                    },
                },
            },
            MuiInputLabel: {
                styleOverrides: {
                    root: {
                        fontWeight: 400,
                    },
                },
            },
            MuiAlert: {
                styleOverrides: {
                    root: {
                        borderRadius: 0,
                    },
                    standardInfo: {
                        backgroundColor: alpha(theme.palette.primary.main, isDark ? 0.14 : 0.08),
                    },
                },
            },
            MuiAvatar: {
                styleOverrides: {
                    root: {
                        fontWeight: 400,
                    },
                },
            },
            MuiDrawer: {
                styleOverrides: {
                    paper: {
                        borderRadius: 0,
                        borderRight: "none",
                        backgroundColor: isDark ? darkPaper : cream,
                    },
                },
            },
            MuiListItemButton: {
                styleOverrides: {
                    root: {
                        borderRadius: 0,
                        minHeight: 48,
                        "&.Mui-selected": {
                            backgroundColor: alpha(theme.palette.primary.main, isDark ? 0.18 : 0.1),
                            color: theme.palette.primary.main,
                            "& .MuiListItemIcon-root": {
                                color: theme.palette.primary.main,
                            },
                        },
                        "&:hover": {
                            backgroundColor: alpha(theme.palette.primary.main, isDark ? 0.12 : 0.06),
                        },
                    },
                },
            },
            MuiTableCell: {
                styleOverrides: {
                    head: {
                        fontWeight: 400,
                        color: theme.palette.text.secondary,
                        backgroundColor: alpha(theme.palette.primary.main, isDark ? 0.1 : 0.04),
                    },
                },
            },
            MuiTooltip: {
                styleOverrides: {
                    tooltip: {
                        borderRadius: 0,
                        backgroundColor: alpha(theme.palette.text.primary, 0.9),
                        color: theme.palette.background.paper,
                        fontSize: "0.78rem",
                    },
                },
            },
            MuiSkeleton: {
                defaultProps: {
                    animation: "wave",
                },
            },
        },
    });
}

export const lightTheme = buildTheme("light");
export const darkTheme = buildTheme("dark");

export type ColorMode = "light" | "dark" | "system";
