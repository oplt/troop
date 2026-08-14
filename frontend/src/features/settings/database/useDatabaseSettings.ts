import { useState } from "react";

import type { SettingsTabValue } from "../types";

export function useDatabaseSettings() {
    const [databaseDirty, setDatabaseDirty] = useState(false);
    const [leaveTabTarget, setLeaveTabTarget] = useState<SettingsTabValue | null>(null);

    const requestTabChange = (activeTab: SettingsTabValue, nextTab: SettingsTabValue, onTabChange: (tab: SettingsTabValue) => void) => {
        if (nextTab === activeTab) return;
        if (databaseDirty && activeTab === "database") {
            setLeaveTabTarget(nextTab);
            return;
        }
        onTabChange(nextTab);
    };

    const confirmLeaveTab = (onTabChange: (tab: SettingsTabValue) => void) => {
        if (!leaveTabTarget) return;
        onTabChange(leaveTabTarget);
        setLeaveTabTarget(null);
    };

    return {
        databaseDirty,
        setDatabaseDirty,
        leaveTabTarget,
        setLeaveTabTarget,
        requestTabChange,
        confirmLeaveTab,
    };
}
