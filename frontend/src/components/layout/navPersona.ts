import type { NavItemDef, NavPersona } from "./navConfig";

export const NAV_PERSONA_STORAGE_KEY = "troop.navPersona";

export type NavPersonaContext = {
    isAdmin: boolean;
    workspaceRole?: string | null;
};

/** Map workspace membership (+ platform admin) to a default navigation persona. */
export function deriveNavPersona(ctx: NavPersonaContext): NavPersona {
    if (ctx.isAdmin) {
        return "admin";
    }
    const role = ctx.workspaceRole?.trim().toLowerCase();
    if (role === "owner" || role === "admin") {
        return "admin";
    }
    if (role === "builder") {
        return "builder";
    }
    return "operator";
}

export function readNavPersonaPreference(): NavPersona | null {
    try {
        const raw = localStorage.getItem(NAV_PERSONA_STORAGE_KEY);
        if (raw === "operator" || raw === "builder" || raw === "admin") {
            return raw;
        }
    } catch {
        // Ignore private browsing / quota failures.
    }
    return null;
}

export function writeNavPersonaPreference(persona: NavPersona) {
    try {
        localStorage.setItem(NAV_PERSONA_STORAGE_KEY, persona);
    } catch {
        // Ignore persistence failures.
    }
}

export function resolveNavPersona(ctx: NavPersonaContext): NavPersona {
    return readNavPersonaPreference() ?? deriveNavPersona(ctx);
}

export function isPrimaryNavItemForPersona(item: NavItemDef, persona: NavPersona): boolean {
    return item.primaryPersonas.includes(persona);
}

export function partitionNavItemsForPersona(items: NavItemDef[], persona: NavPersona) {
    const primary: NavItemDef[] = [];
    const advanced: NavItemDef[] = [];
    for (const item of items) {
        if (isPrimaryNavItemForPersona(item, persona)) {
            primary.push(item);
        } else {
            advanced.push(item);
        }
    }
    return { primary, advanced };
}

export const NAV_PERSONA_LABELS: Record<NavPersona, string> = {
    operator: "Operator",
    builder: "Builder",
    admin: "Admin",
};
