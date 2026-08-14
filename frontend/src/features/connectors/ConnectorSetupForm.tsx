import { Stack, Typography } from "@mui/material";
import type { ConnectorManifest } from "../../api/integrations";
import { ConnectorManifestCapabilities, ConnectorSetupOverrideNotice } from "./ConnectorScopeCapabilities";
import { JsonSchemaFields } from "./JsonSchemaFields";

export function ConnectorSetupForm({
    manifest,
    values,
    onChange,
}: {
    manifest: ConnectorManifest | undefined;
    values: Record<string, unknown>;
    onChange: (key: string, value: unknown) => void;
}) {
    if (!manifest) return null;
    const usesOAuth = manifest.auth.type === "oauth2";
    return (
        <Stack spacing={1.5}>
            <ConnectorSetupOverrideNotice manifest={manifest} />
            <ConnectorManifestCapabilities manifest={manifest} />
            {!usesOAuth && (
                <JsonSchemaFields
                    schema={manifest.auth.config_schema}
                    values={values}
                    onChange={onChange}
                />
            )}
        </Stack>
    );
}

export function ConnectorOperationFields({
    manifest,
    operationSlug,
    values,
    onChange,
}: {
    manifest: ConnectorManifest | undefined;
    operationSlug: string;
    values: Record<string, unknown>;
    onChange: (key: string, value: unknown) => void;
}) {
    const operation = [...(manifest?.triggers ?? []), ...(manifest?.actions ?? [])]
        .find((item) => item.slug === operationSlug);
    if (!operation?.input_schema || Object.keys(operation.input_schema).length === 0) return null;
    return (
        <Stack spacing={1.5}>
            {operation.description ? (
                <Typography variant="body2" color="text.secondary">{operation.description}</Typography>
            ) : null}
            {operation.requires_approval ? (
                <Typography variant="caption" color="warning.main">
                    Requires approval · {operation.risk_level} risk
                </Typography>
            ) : null}
            <JsonSchemaFields
                schema={operation.input_schema}
                values={values}
                onChange={onChange}
            />
        </Stack>
    );
}
