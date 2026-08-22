import type { ConnectorManifest, ConnectorOperationManifest } from "../../api/integrations";
import { humanizeKey } from "../../utils/formatters";

type JsonSchema = Record<string, unknown>;
type ConnectorDefinitionLike = {
    id?: string;
    slug: string;
    name: string;
    description: string;
    provider_type: string;
    config_schema_json: Record<string, unknown>;
    metadata_json?: Record<string, unknown>;
};

export function schemaProperties(schema: JsonSchema | undefined): Record<string, JsonSchema> {
    const properties = schema?.properties;
    if (!properties || typeof properties !== "object" || Array.isArray(properties)) return {};
    return properties as Record<string, JsonSchema>;
}

export function schemaRequiredKeys(schema: JsonSchema | undefined): Set<string> {
    const required = schema?.required;
    return new Set(Array.isArray(required) ? required.filter((item): item is string => typeof item === "string") : []);
}

export function findManifestOperation(
    manifest: ConnectorManifest | undefined,
    slug: string,
): ConnectorOperationManifest | undefined {
    if (!manifest || !slug) return undefined;
    return [...manifest.triggers, ...manifest.actions].find((item) => item.slug === slug);
}

export function manifestForProvider(
    manifests: ConnectorManifest[] | undefined,
    providerSlug: string,
): ConnectorManifest | undefined {
    return manifests?.find((item) => item.provider_slug === providerSlug);
}

export function scopeCapabilityLabel(
    scope: string,
    manifest: ConnectorManifest | undefined,
): { label: string; description: string } {
    const match = manifest?.auth.scopes.find((item) => item.scope === scope);
    if (match) {
        return { label: match.label, description: match.description };
    }
    return { label: humanizeKey(scope.split("/").pop() ?? scope), description: scope };
}

export function formatScopeCapabilities(
    scopes: string[],
    manifest: ConnectorManifest | undefined,
): Array<{ scope: string; label: string; description: string }> {
    return scopes.map((scope) => ({
        scope,
        ...scopeCapabilityLabel(scope, manifest),
    }));
}

export function listManifestTriggers(manifest: ConnectorManifest | undefined): ConnectorOperationManifest[] {
    return manifest?.triggers ?? [];
}

export function secretFieldNames(schema: JsonSchema | undefined): Set<string> {
    const names = new Set<string>();
    for (const [key, property] of Object.entries(schemaProperties(schema))) {
        const format = String(property.format ?? "");
        if (/(token|secret|password|api_key)/i.test(key) || format === "password") {
            names.add(key);
        }
    }
    return names;
}

export function manifestFromDefinition(definition: ConnectorDefinitionLike | undefined): ConnectorManifest | undefined {
    if (!definition) return undefined;
    return {
        provider_slug: definition.slug,
        version: "1.0.0",
        name: definition.name,
        description: definition.description,
        provider_type: definition.provider_type,
        auth: {
            type: definition.provider_type === "native" ? "none" : "api_key",
            scopes: [],
            config_schema: definition.config_schema_json,
            reauthorization: "manual",
            pkce_required: false,
        },
        triggers: [],
        actions: [],
        webhook: null,
        health: null,
        rate_limits: null,
        metadata: definition.metadata_json ?? {},
    };
}

export function resolveSetupManifest(
    manifests: ConnectorManifest[] | undefined,
    definitions: ConnectorDefinitionLike[] | undefined,
    providerSlug: string,
): ConnectorManifest | undefined {
    return manifestForProvider(manifests, providerSlug)
        ?? manifestFromDefinition(definitions?.find((item) => item.slug === providerSlug));
}
