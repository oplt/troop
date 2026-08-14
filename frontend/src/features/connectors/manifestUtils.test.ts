import { describe, expect, it } from "vitest";
import { normalizeConnectorManifest } from "../../api/integrations";
import { formatScopeCapabilities, manifestFromDefinition, resolveSetupManifest } from "./manifestUtils";

describe("connector manifest utils", () => {
    it("maps granted scopes to human-readable capability labels", () => {
        const manifest = normalizeConnectorManifest({
            provider_slug: "gmail",
            version: "1.0.0",
            name: "Gmail",
            auth: {
                type: "oauth2",
                scopes: [{
                    scope: "https://www.googleapis.com/auth/gmail.readonly",
                    label: "Read mail",
                    description: "Search and read messages",
                    required_for: ["search_messages"],
                }],
            },
            triggers: [],
            actions: [],
        });
        expect(formatScopeCapabilities(["https://www.googleapis.com/auth/gmail.readonly"], manifest)).toEqual([
            {
                scope: "https://www.googleapis.com/auth/gmail.readonly",
                label: "Read mail",
                description: "Search and read messages",
            },
        ]);
    });

    it("falls back to connector definition config schema when manifest is missing", () => {
        const manifest = resolveSetupManifest([], [{
            id: "1",
            slug: "mcp-http",
            name: "MCP HTTP Server",
            description: "",
            provider_type: "mcp",
            config_schema_json: {
                type: "object",
                properties: { base_url: { type: "string" } },
                required: ["base_url"],
            },
            metadata_json: {},
        }], "mcp-http");
        expect(manifest?.auth.config_schema).toMatchObject({
            properties: { base_url: { type: "string" } },
        });
    });

    it("builds a setup manifest from connector definitions", () => {
        expect(manifestFromDefinition({
            id: "2",
            slug: "telegram",
            name: "Telegram Bot",
            description: "",
            provider_type: "native",
            config_schema_json: { properties: { bot_token: { type: "string" } } },
            metadata_json: {},
        })?.auth.config_schema).toEqual({ properties: { bot_token: { type: "string" } } });
    });
});
