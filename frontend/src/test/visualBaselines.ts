/**
 * Landmark / structure baselines for visual + IA regression without Playwright.
 * Update intentionally when shell IA changes; keep in sync with AppLayout + key pages.
 */
export const VISUAL_BASELINES = {
    shell: {
        skipLink: "Skip to main content",
        mainId: "main-content",
        appBarLandmark: "banner",
        navLandmark: "navigation",
        mainLandmark: "main",
        drawerWidths: { expanded: 288, collapsed: 96 },
        toolbarHeights: { xs: 64, md: 72 },
    },
    pages: [
        { route: "/dashboard", titleHints: ["Do next", "Projects"], shell: true },
        { route: "/", titleHints: ["Welcome back", "Sign in"], shell: false },
        { route: "/projects", titleHints: ["Projects"], shell: true },
        { route: "/approvals", titleHints: ["Approvals"], shell: true },
        { route: "/portfolio", titleHints: ["Portfolio"], shell: true },
        { route: "/hierarchy", titleHints: ["Hierarchy"], shell: true },
        { route: "/analytics/cost", titleHints: ["Cost"], shell: true },
    ],
} as const;
