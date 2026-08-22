import { alpha, createTheme, type PaletteMode } from "@mui/material/styles";

/**
 * Tesla-inspired design tokens from DESIGN.md.
 * Universal Sans is proprietary — product UI ships Space Grotesk (Display)
 * + DM Sans (Text) as the licensed geometric Display/Text split. See PRODUCT.md.
 */
const tokens = {
    electricBlue: "#3E6AE1",
    electricBlueHover: "#3459C8",
    white: "#FFFFFF",
    lightAsh: "#F4F4F4",
    carbonDark: "#171A20",
    graphite: "#393C41",
    pewter: "#5C5E62",
    silverFog: "#8E8E8E",
    cloudGray: "#EEEEEE",
    paleSilver: "#D0D1D2",
    frostedGlass: "rgba(255, 255, 255, 0.75)",
    overlay: "rgba(128, 128, 128, 0.65)",
    transition: "0.33s cubic-bezier(0.5, 0, 0, 0.75)",
    fontDisplay:
        "'Space Grotesk', -apple-system, BlinkMacSystemFont, Arial, sans-serif",
    fontText:
        "'DM Sans', -apple-system, BlinkMacSystemFont, Arial, sans-serif",
} as const;

function buildTheme(mode: PaletteMode) {
    const isDark = mode === "dark";

    const theme = createTheme({
        palette: {
            mode,
            primary: {
                main: tokens.electricBlue,
                light: tokens.electricBlue,
                dark: tokens.electricBlueHover,
                contrastText: tokens.white,
            },
            secondary: {
                main: tokens.graphite,
                light: tokens.pewter,
                dark: tokens.carbonDark,
                contrastText: tokens.white,
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
                main: tokens.electricBlue,
            },
            background: {
                default: isDark ? tokens.carbonDark : tokens.white,
                paper: isDark ? "#1E2128" : tokens.white,
            },
            text: {
                primary: isDark ? tokens.white : tokens.carbonDark,
                secondary: isDark ? alpha(tokens.white, 0.72) : tokens.graphite,
                disabled: tokens.silverFog,
            },
            divider: isDark ? alpha(tokens.white, 0.11) : tokens.cloudGray,
            grey: {
                50: tokens.lightAsh,
                100: tokens.cloudGray,
                200: tokens.paleSilver,
                300: tokens.paleSilver,
                400: tokens.silverFog,
                500: tokens.pewter,
                600: tokens.graphite,
                700: tokens.carbonDark,
                800: tokens.carbonDark,
                900: tokens.carbonDark,
            },
        },
        shape: {
            borderRadius: 4,
        },
        spacing: 8,
        transitions: {
            duration: {
                shortest: 200,
                shorter: 250,
                short: 300,
                standard: 330,
                complex: 330,
                enteringScreen: 330,
                leavingScreen: 330,
            },
            easing: {
                easeInOut: "cubic-bezier(0.5, 0, 0, 0.75)",
                easeOut: "cubic-bezier(0.5, 0, 0, 0.75)",
                easeIn: "cubic-bezier(0.5, 0, 0, 0.75)",
                sharp: "cubic-bezier(0.5, 0, 0, 0.75)",
            },
        },
        typography: {
            fontFamily: tokens.fontText,
            h1: {
                fontFamily: tokens.fontDisplay,
                fontSize: "2.5rem",
                fontWeight: 500,
                letterSpacing: "normal",
                lineHeight: 1.2,
            },
            h2: {
                fontFamily: tokens.fontDisplay,
                fontSize: "1.75rem",
                fontWeight: 500,
                letterSpacing: "normal",
                lineHeight: 1.2,
            },
            h3: {
                fontFamily: tokens.fontDisplay,
                fontSize: "1.5rem",
                fontWeight: 500,
                letterSpacing: "normal",
                lineHeight: 1.2,
            },
            h4: {
                fontFamily: tokens.fontText,
                fontSize: "1.25rem",
                fontWeight: 500,
                letterSpacing: "normal",
                lineHeight: 1.35,
            },
            h5: {
                fontSize: "1.0625rem",
                fontWeight: 500,
                letterSpacing: "normal",
                lineHeight: 1.18,
            },
            h6: {
                fontSize: "0.875rem",
                fontWeight: 500,
                letterSpacing: "normal",
                lineHeight: 1.2,
            },
            subtitle1: {
                fontSize: "0.875rem",
                fontWeight: 500,
                lineHeight: 1.2,
            },
            subtitle2: {
                fontSize: "0.875rem",
                fontWeight: 500,
                lineHeight: 1.2,
            },
            body1: {
                fontSize: "0.875rem",
                lineHeight: 1.43,
                fontWeight: 400,
            },
            body2: {
                fontSize: "0.875rem",
                lineHeight: 1.43,
                fontWeight: 400,
            },
            button: {
                fontSize: "0.875rem",
                fontWeight: 500,
                textTransform: "none",
                letterSpacing: "normal",
                lineHeight: 1.2,
            },
            overline: {
                fontSize: "0.875rem",
                fontWeight: 400,
                letterSpacing: "normal",
                textTransform: "none",
                lineHeight: 1.43,
                color: isDark ? alpha(tokens.white, 0.62) : tokens.pewter,
            },
            caption: {
                fontSize: "0.8125rem",
                lineHeight: 1.43,
                fontWeight: 400,
            },
        },
        shadows: [
            "none",
            "none",
            "none",
            "none",
            "none",
            "none",
            "none",
            "none",
            "none",
            "none",
            "none",
            "none",
            "none",
            "none",
            "none",
            "none",
            "none",
            "none",
            "none",
            "none",
            "none",
            "none",
            "none",
            "none",
            "none",
        ],
    });

    return createTheme(theme, {
        components: {
            MuiTypography: {
                defaultProps: {
                    variantMapping: {
                        h1: "h1",
                        h2: "h2",
                        h3: "h3",
                        h4: "h4",
                        h5: "h5",
                        h6: "h6",
                        subtitle1: "p",
                        subtitle2: "p",
                        body1: "p",
                        body2: "p",
                        inherit: "p",
                    },
                },
            },
            MuiCssBaseline: {
                styleOverrides: {
                    ":root": {
                        colorScheme: mode,
                        "--tesla-electric-blue": tokens.electricBlue,
                        "--tesla-carbon-dark": tokens.carbonDark,
                        "--tesla-graphite": tokens.graphite,
                        "--tesla-pewter": tokens.pewter,
                        "--tesla-light-ash": tokens.lightAsh,
                        "--tesla-transition": tokens.transition,
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
                        backgroundColor: alpha(tokens.electricBlue, 0.22),
                    },
                    a: {
                        color: isDark ? alpha(tokens.white, 0.78) : tokens.pewter,
                        textDecoration: "none",
                        transition: `color ${tokens.transition}, box-shadow ${tokens.transition}`,
                        "&:hover": {
                            textDecoration: "underline",
                        },
                    },
                },
            },
            MuiAppBar: {
                defaultProps: {
                    elevation: 0,
                },
                styleOverrides: {
                    root: {
                        backgroundImage: "none",
                        boxShadow: "none",
                        borderBottom: "none",
                    },
                },
            },
            MuiCard: {
                defaultProps: {
                    elevation: 0,
                },
                styleOverrides: {
                    root: {
                        borderRadius: 4,
                        border: `1px solid ${theme.palette.divider}`,
                        backgroundColor: theme.palette.background.paper,
                        boxShadow: "none",
                    },
                },
            },
            MuiPaper: {
                defaultProps: {
                    elevation: 0,
                },
                styleOverrides: {
                    root: {
                        backgroundImage: "none",
                        borderRadius: 4,
                        boxShadow: "none",
                    },
                    outlined: {
                        borderColor: theme.palette.divider,
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
                        padding: "4px 16px",
                        borderRadius: 4,
                        border: "3px solid transparent",
                        boxShadow: "rgba(0,0,0,0) 0px 0px 0px 2px inset",
                        transition: `border-color 0.33s, background-color 0.33s, color 0.33s, box-shadow 0.25s`,
                        "&:hover": {
                            transform: "none",
                        },
                    },
                    contained: {
                        "&.MuiButton-containedPrimary": {
                            backgroundColor: tokens.electricBlue,
                            color: tokens.white,
                            "&:hover": {
                                backgroundColor: tokens.electricBlueHover,
                            },
                        },
                        "&.MuiButton-containedSecondary": {
                            backgroundColor: isDark ? alpha(tokens.white, 0.08) : tokens.white,
                            color: isDark ? tokens.white : tokens.graphite,
                            border: `1px solid ${isDark ? alpha(tokens.white, 0.18) : tokens.cloudGray}`,
                            "&:hover": {
                                backgroundColor: isDark ? alpha(tokens.white, 0.12) : tokens.lightAsh,
                            },
                        },
                    },
                    outlined: {
                        borderColor: isDark ? alpha(tokens.white, 0.18) : tokens.paleSilver,
                        color: isDark ? tokens.white : tokens.graphite,
                        backgroundColor: "transparent",
                        "&:hover": {
                            backgroundColor: isDark
                                ? alpha(tokens.white, 0.06)
                                : tokens.lightAsh,
                            borderColor: isDark ? alpha(tokens.white, 0.28) : tokens.paleSilver,
                        },
                    },
                    text: {
                        color: isDark ? alpha(tokens.white, 0.78) : tokens.pewter,
                        minHeight: 32,
                        "&:hover": {
                            backgroundColor: isDark
                                ? alpha(tokens.white, 0.06)
                                : alpha(tokens.carbonDark, 0.04),
                            textDecoration: "underline",
                        },
                    },
                    sizeSmall: {
                        minHeight: 32,
                        padding: "4px 12px",
                    },
                },
            },
            MuiIconButton: {
                styleOverrides: {
                    root: {
                        borderRadius: 4,
                        transition: `color 0.33s, background-color 0.33s`,
                        "&:hover": {
                            transform: "none",
                        },
                    },
                },
            },
            MuiChip: {
                styleOverrides: {
                    root: {
                        borderRadius: 4,
                        fontWeight: 500,
                        fontSize: "0.875rem",
                    },
                    outlined: {
                        borderColor: isDark ? alpha(tokens.white, 0.18) : tokens.paleSilver,
                    },
                },
            },
            MuiOutlinedInput: {
                styleOverrides: {
                    root: {
                        borderRadius: 4,
                        backgroundColor: "transparent",
                        transition: `border-color 0.33s, background-color 0.33s`,
                        "&:hover .MuiOutlinedInput-notchedOutline": {
                            borderColor: isDark ? alpha(tokens.white, 0.28) : tokens.paleSilver,
                        },
                        "&.Mui-focused": {
                            boxShadow: "none",
                        },
                        "&.Mui-focused .MuiOutlinedInput-notchedOutline": {
                            borderColor: tokens.electricBlue,
                            borderWidth: 1,
                        },
                    },
                    notchedOutline: {
                        borderColor: isDark ? alpha(tokens.white, 0.14) : tokens.paleSilver,
                    },
                    input: {
                        paddingBlock: 10,
                        "&::placeholder": {
                            color: tokens.silverFog,
                            opacity: 1,
                        },
                    },
                },
            },
            MuiInputLabel: {
                styleOverrides: {
                    root: {
                        fontWeight: 500,
                        fontSize: "0.875rem",
                    },
                },
            },
            MuiAlert: {
                styleOverrides: {
                    root: {
                        borderRadius: 4,
                        boxShadow: "none",
                    },
                },
            },
            MuiAvatar: {
                styleOverrides: {
                    root: {
                        fontWeight: 500,
                    },
                },
            },
            MuiDrawer: {
                styleOverrides: {
                    paper: {
                        borderRadius: 0,
                        borderRight: `1px solid ${theme.palette.divider}`,
                        backgroundColor: theme.palette.background.default,
                        boxShadow: "none",
                    },
                },
            },
            MuiListItemButton: {
                styleOverrides: {
                    root: {
                        borderRadius: 4,
                        minHeight: 40,
                        padding: "4px 16px",
                        transition: `color 0.33s, background-color 0.33s`,
                        "&.Mui-selected": {
                            backgroundColor: alpha(tokens.carbonDark, isDark ? 0.12 : 0.06),
                            color: theme.palette.text.primary,
                            "& .MuiListItemIcon-root": {
                                color: theme.palette.text.primary,
                            },
                        },
                        "&:hover": {
                            backgroundColor: alpha(tokens.carbonDark, isDark ? 0.08 : 0.04),
                        },
                    },
                },
            },
            MuiTableCell: {
                styleOverrides: {
                    head: {
                        fontWeight: 500,
                        color: theme.palette.text.secondary,
                        backgroundColor: isDark ? alpha(tokens.white, 0.04) : tokens.lightAsh,
                        borderBottom: `1px solid ${theme.palette.divider}`,
                    },
                },
            },
            MuiTooltip: {
                styleOverrides: {
                    tooltip: {
                        borderRadius: 4,
                        backgroundColor: isDark ? tokens.white : tokens.carbonDark,
                        color: isDark ? tokens.carbonDark : tokens.white,
                        fontSize: "0.8125rem",
                        fontWeight: 400,
                        boxShadow: "none",
                    },
                },
            },
            MuiSkeleton: {
                defaultProps: {
                    animation: "wave",
                },
                styleOverrides: {
                    rounded: {
                        borderRadius: 4,
                    },
                },
            },
            MuiLinearProgress: {
                styleOverrides: {
                    root: {
                        borderRadius: 4,
                        height: 6,
                    },
                },
            },
            MuiDialog: {
                styleOverrides: {
                    paper: {
                        borderRadius: 4,
                        boxShadow: "none",
                        border: `1px solid ${theme.palette.divider}`,
                    },
                },
            },
            MuiMenu: {
                styleOverrides: {
                    paper: {
                        borderRadius: 4,
                        boxShadow: "none",
                        border: `1px solid ${theme.palette.divider}`,
                    },
                },
            },
            MuiDivider: {
                styleOverrides: {
                    root: {
                        borderColor: theme.palette.divider,
                    },
                },
            },
            MuiBreadcrumbs: {
                styleOverrides: {
                    separator: {
                        color: isDark ? alpha(tokens.white, 0.55) : tokens.pewter,
                    },
                },
            },
            MuiLink: {
                styleOverrides: {
                    root: {
                        color: isDark ? alpha(tokens.white, 0.78) : tokens.pewter,
                        fontWeight: 400,
                        transition: `color 0.33s, box-shadow 0.33s cubic-bezier(0.5, 0, 0, 0.75)`,
                        "&:hover": {
                            color: isDark ? tokens.white : tokens.graphite,
                            textDecoration: "underline",
                        },
                    },
                },
            },
        },
    });
}

export const lightTheme = buildTheme("light");
export const darkTheme = buildTheme("dark");

export type ColorMode = "light" | "dark" | "system";

export { tokens as designTokens };
