import {
    Alert,
    Box,
    Button,
    MenuItem,
    Stack,
    Switch,
    TextField,
    Typography,
} from "@mui/material";

import type { ModuleCatalogItem, ModulePack } from "../../../api/platform";
import { SectionCard } from "../../../components/ui/SectionCard";
import { compactBorderedPanelSx } from "../styles";
import type { ConfigDraft } from "../types";
import { ModulePackEditor } from "./ModulePackEditor";

type PlatformConfigPanelProps = {
    configDraft: ConfigDraft;
    moduleCatalog: ModuleCatalogItem[];
    packOptions: ModulePack[];
    activePackSummary: ModulePack | undefined;
    isSaving: boolean;
    saveError: unknown;
    onConfigDraftChange: (updater: (current: ConfigDraft) => ConfigDraft) => void;
    onSave: () => void;
};

export function PlatformConfigPanel({
    configDraft,
    moduleCatalog,
    packOptions,
    activePackSummary,
    isSaving,
    saveError,
    onConfigDraftChange,
    onSave,
}: PlatformConfigPanelProps) {
    return (
        <SectionCard
            title="Clone configuration"
            description="Set the product name, core domain terminology, module pack, and module visibility defaults."
            action={
                <Button variant="contained" disabled={isSaving} onClick={onSave}>
                    {isSaving ? "Saving..." : "Save platform config"}
                </Button>
            }
        >
            <Stack spacing={2.5}>
                {saveError ? (
                    <Alert severity="error">
                        {saveError instanceof Error
                            ? saveError.message
                            : "Couldn't save platform config. Try again."}
                    </Alert>
                ) : null}
                <TextField
                    label="App name"
                    value={configDraft.app_name}
                    onChange={(event) =>
                        onConfigDraftChange((current) => ({ ...current, app_name: event.target.value }))
                    }
                    fullWidth
                />
                <Box
                    sx={{
                        display: "grid",
                        gap: 1.5,
                        gridTemplateColumns: { xs: "1fr", md: "repeat(2, minmax(0, 1fr))" },
                    }}
                >
                    <TextField
                        label="Core domain singular"
                        value={configDraft.core_domain_singular}
                        onChange={(event) =>
                            onConfigDraftChange((current) => ({
                                ...current,
                                core_domain_singular: event.target.value,
                            }))
                        }
                        fullWidth
                    />
                    <TextField
                        label="Core domain plural"
                        value={configDraft.core_domain_plural}
                        onChange={(event) =>
                            onConfigDraftChange((current) => ({
                                ...current,
                                core_domain_plural: event.target.value,
                            }))
                        }
                        fullWidth
                    />
                </Box>
                <TextField
                    label="Module pack"
                    select
                    value={configDraft.module_pack}
                    helperText="Preset of which product areas appear in nav (work, agents, automate…). Changing pack resets module toggles below."
                    onChange={(event) => {
                        const nextPack = event.target.value;
                        const packDefaults =
                            packOptions.find((pack) => pack.key === nextPack)?.modules ?? [];
                        onConfigDraftChange((current) => ({
                            ...current,
                            module_pack: nextPack,
                            module_states: Object.fromEntries(
                                moduleCatalog.map((item) => [item.key, packDefaults.includes(item.key)]),
                            ),
                        }));
                    }}
                    fullWidth
                >
                    {packOptions.map((pack) => (
                        <MenuItem key={pack.key} value={pack.key}>
                            {pack.label}
                        </MenuItem>
                    ))}
                </TextField>
                {activePackSummary ? <Alert severity="info">{activePackSummary.description}</Alert> : null}

                <Box sx={compactBorderedPanelSx}>
                    <Stack direction="row" justifyContent="space-between" spacing={1.5}>
                        <Box>
                            <Typography variant="subtitle2">MFA authentication</Typography>
                            <Typography variant="body2" color="text.secondary">
                                Show the authenticator code field on the login page.
                            </Typography>
                        </Box>
                        <Switch
                            checked={configDraft.mfa_enabled}
                            onChange={(event) =>
                                onConfigDraftChange((current) => ({
                                    ...current,
                                    mfa_enabled: event.target.checked,
                                }))
                            }
                        />
                    </Stack>
                </Box>

                <ModulePackEditor
                    moduleCatalog={moduleCatalog}
                    configDraft={configDraft}
                    onConfigDraftChange={onConfigDraftChange}
                />
            </Stack>
        </SectionCard>
    );
}
