import { describe, expect, it } from "vitest";
import { normalizeConnectorDefinition, normalizeConnectorManifest, normalizeConnectorOperation, normalizeConnectorStatus } from "./integrations";

describe("integration API normalization", () => {
    it("normalizes connector aliases without exposing unrelated fields", () => {
        expect(normalizeConnectorDefinition({
            id: "gmail",
            key: "gmail",
            name: "Gmail",
            config_schema: { type: "object" },
            metadata: { native: true },
        })).toMatchObject({
            id: "gmail",
            slug: "gmail",
            provider_type: "native",
            config_schema_json: { type: "object" },
        });
    });

    it("normalizes operation scopes and safe defaults", () => {
        expect(normalizeConnectorOperation({
            slug: "gmail.send_draft",
            operation_type: "action",
            required_scopes_json: ["gmail.send"],
            requires_approval: true,
            risk_level: "high",
        })).toMatchObject({
            slug: "gmail.send_draft",
            operation_type: "action",
            required_scopes: ["gmail.send"],
            requires_approval: true,
            risk_level: "high",
        });
    });

    it("normalizes connector manifest scopes and operations", () => {
        expect(normalizeConnectorManifest({
            provider_slug: "gmail",
            version: "1.0.0",
            name: "Gmail",
            auth: {
                type: "oauth2",
                scopes: [{ scope: "scope-a", label: "Scope A", description: "desc", required_for: ["x"] }],
                config_schema: { type: "object" },
                pkce_required: true,
            },
            actions: [{
                slug: "gmail.get_thread",
                name: "Get thread",
                operation_kind: "read",
                input_schema: { type: "object", properties: { thread_id: { type: "string" } } },
                requires_approval: false,
                risk_level: "low",
            }],
        })).toMatchObject({
            provider_slug: "gmail",
            auth: { type: "oauth2", pkce_required: true, scopes: [{ label: "Scope A" }] },
            actions: [{ slug: "gmail.get_thread", input_schema: { properties: { thread_id: { type: "string" } } } }],
        });
    });

    it("accepts nested installation status responses", () => {
        expect(normalizeConnectorStatus("gmail", {
            installation: { id: "i1", name: "person@example.com", status: "active" },
            scopes: ["gmail.readonly"],
        })).toMatchObject({
            provider: "gmail",
            installation_id: "i1",
            account_label: "person@example.com",
            status: "active",
            granted_scopes: ["gmail.readonly"],
        });
    });
});
