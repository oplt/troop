import { describe, expect, it } from "vitest";
import { emailTelegramStarter, safeRunValue, toWorkflowPayload, validateWorkflow } from "./builderState";

describe("workflow builder state", () => {
    it("preserves the backend nodes/edges contract", () => {
        const starter = emailTelegramStarter();
        const payload = toWorkflowPayload(starter.nodes, starter.edges);
        expect(payload.entry_node_id).toBe("gmail_trigger");
        expect(payload.nodes[0]).toMatchObject({ id: "gmail_trigger", type: "trigger", config: { event_type: "gmail_new_message" } });
        expect(payload.edges[0]).toMatchObject({ from: "gmail_trigger", to: "get_thread" });
    });

    it("requires explicit connector installation bindings", () => {
        const starter = emailTelegramStarter();
        expect(validateWorkflow(starter.nodes, starter.edges)).toContain("Gmail: new email: select an explicit connection.");
        const bound = starter.nodes.map((node) =>
            ["trigger", "tool"].includes(node.data.nodeType)
                ? { ...node, data: { ...node.data, config: { ...node.data.config, connector_installation_id: "install-1" } } }
                : node,
        );
        expect(validateWorkflow(bound, starter.edges)).toEqual([]);
    });

    it("redacts secret-shaped keys recursively from run metadata", () => {
        expect(safeRunValue({
            message_id: "safe",
            access_token: "secret",
            nested: { webhook_secret: "secret", thread_id: "thread" },
        })).toEqual({ message_id: "safe", nested: { thread_id: "thread" } });
    });
});
