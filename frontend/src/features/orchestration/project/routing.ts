import type { DetailTab, KnowledgeView, TeamView, WorkView } from "./queries";

export const PROJECT_DETAIL_TABS = [
    "overview",
    "board",
    "runs",
    "agents",
    "memory",
    "settings",
] as const satisfies readonly DetailTab[];

export function isProjectDetailTab(value: string | null | undefined): value is DetailTab {
    return Boolean(value && (PROJECT_DETAIL_TABS as readonly string[]).includes(value));
}

/** Resolve the active workspace tab from a URL search param. */
export function parseProjectDetailTab(tabParam: string | null): DetailTab {
    return isProjectDetailTab(tabParam) ? tabParam : "overview";
}

/** Sync local tab state when the URL changes; returns null when the param is invalid. */
export function syncProjectDetailTabFromSearchParam(tabParam: string | null): DetailTab | null {
    return isProjectDetailTab(tabParam) ? tabParam : null;
}

export function withProjectDetailTab(params: URLSearchParams, tab: DetailTab): URLSearchParams {
    const next = new URLSearchParams(params);
    next.set("tab", tab);
    return next;
}

export type ProjectDetailTabSideEffects = {
    workView?: WorkView;
    teamView?: TeamView;
    knowledgeView?: KnowledgeView;
};

/** Sub-view defaults applied when the user selects a top-level tab. */
export function projectDetailTabSideEffects(tab: DetailTab): ProjectDetailTabSideEffects {
    switch (tab) {
        case "board":
            return { workView: "board" };
        case "agents":
            return { teamView: "agents" };
        case "memory":
            return { knowledgeView: "memory" };
        case "settings":
            return { teamView: "settings", knowledgeView: "sources" };
        default:
            return {};
    }
}
