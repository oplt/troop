import type { ParameterCatalogEntry } from "../../api/settings";

export type SettingsTabValue =
    | "database"
    | "providers"
    | "github_sync"
    | "platform"
    | "users"
    | "companies"
    | "profile";

export type DatabaseSettingDraft = {
    value: string;
    description: string;
};

export type DatabaseSettingDrafts = Record<string, DatabaseSettingDraft>;

export type ParameterCatalogMap = Record<string, ParameterCatalogEntry>;

export type NewDatabaseSettingForm = {
    key: string;
    value: string;
    description: string;
};

export const SETTINGS_TABS: SettingsTabValue[] = [
    "providers",
    "github_sync",
    "platform",
    "users",
    "database",
    "companies",
    "profile",
];

export function isSettingsTab(value: string | null): value is SettingsTabValue {
    return value !== null && (SETTINGS_TABS as string[]).includes(value);
}

export function parseSettingsTab(raw: string | null): SettingsTabValue {
    const normalized =
        raw === "ai"
            ? "providers"
            : raw === "github" || raw === "integrations"
              ? "github_sync"
              : raw;
    return isSettingsTab(normalized) ? normalized : "database";
}
