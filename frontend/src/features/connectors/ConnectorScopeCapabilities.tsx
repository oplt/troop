import { Alert, Chip, Stack, Typography } from "@mui/material";
import type { ConnectorManifest } from "../../api/integrations";
import { formatScopeCapabilities } from "./manifestUtils";

export function ConnectorScopeCapabilities({
    manifest,
    grantedScopes,
    title = "Granted capabilities",
}: {
    manifest: ConnectorManifest | undefined;
    grantedScopes: string[];
    title?: string;
}) {
    const capabilities = formatScopeCapabilities(grantedScopes, manifest);
    return (
        <Stack spacing={0.75}>
            <Typography variant="caption" color="text.secondary">{title}</Typography>
            {capabilities.length ? (
                <Stack direction="row" gap={0.75} flexWrap="wrap" useFlexGap>
                    {capabilities.map((item) => (
                        <Chip
                            key={item.scope}
                            label={item.label}
                            size="small"
                            variant="outlined"
                            title={item.description || item.scope}
                        />
                    ))}
                </Stack>
            ) : (
                <Typography variant="body2" color="text.secondary">No scopes reported.</Typography>
            )}
        </Stack>
    );
}

export function ConnectorManifestCapabilities({
    manifest,
}: {
    manifest: ConnectorManifest | undefined;
}) {
    if (!manifest?.auth.scopes.length) return null;
    return (
        <Stack spacing={0.75}>
            <Typography variant="caption" color="text.secondary">Requested capabilities</Typography>
            <Stack direction="row" gap={0.75} flexWrap="wrap" useFlexGap>
                {manifest.auth.scopes.map((scope) => (
                    <Chip
                        key={scope.scope}
                        label={scope.label}
                        size="small"
                        variant="outlined"
                        title={scope.description || scope.scope}
                    />
                ))}
            </Stack>
        </Stack>
    );
}

export function ConnectorSetupOverrideNotice({
    manifest,
}: {
    manifest: ConnectorManifest | undefined;
}) {
    if (!manifest) return null;
    if (manifest.auth.type === "oauth2") {
        return (
            <Alert severity="info">
                {manifest.name} uses OAuth sign-in. Troop stores refresh tokens encrypted and never returns them to the browser.
            </Alert>
        );
    }
    if (manifest.auth.type === "bot_token") {
        return (
            <Alert severity="info">
                Paste the bot token from BotFather. Troop encrypts it at rest and redacts it from API responses.
            </Alert>
        );
    }
    return null;
}
