import { Box } from "@mui/material";
import {
    Extension as ExtensionIcon,
    Flag as FlagIcon,
    MailOutline as MailOutlineIcon,
    Sell as SellIcon,
} from "@mui/icons-material";

import { StatCard } from "../../components/ui/StatCard";
import type { ConfigDraft } from "./types";

type AdminPlatformOverviewProps = {
    configDraft: ConfigDraft;
    planCount: number;
    flagCount: number;
    templateCount: number;
};

export function AdminPlatformOverview({
    configDraft,
    planCount,
    flagCount,
    templateCount,
}: AdminPlatformOverviewProps) {
    const enabledModuleCount = Object.values(configDraft.module_states).filter(Boolean).length;

    return (
        <Box
            sx={{
                display: "grid",
                gap: 2,
                gridTemplateColumns: {
                    xs: "1fr",
                    sm: "repeat(2, minmax(0, 1fr))",
                    xl: "repeat(4, minmax(0, 1fr))",
                },
            }}
        >
            <StatCard
                label="Enabled modules"
                value={enabledModuleCount}
                description="Modules currently exposed by the selected pack and overrides"
                icon={<ExtensionIcon />}
            />
            <StatCard
                label="Subscription plans"
                value={planCount}
                description="Commercial tiers available across the platform"
                icon={<SellIcon />}
                color="secondary"
            />
            <StatCard
                label="Feature flags"
                value={flagCount}
                description="Flags available for rollout and experimentation"
                icon={<FlagIcon />}
                color="success"
            />
            <StatCard
                label="Email templates"
                value={templateCount}
                description="Transactional templates ready for automated delivery"
                icon={<MailOutlineIcon />}
                color="warning"
            />
        </Box>
    );
}
