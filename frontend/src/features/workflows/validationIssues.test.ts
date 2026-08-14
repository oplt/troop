import { describe, expect, it } from "vitest";
import { clientValidationIssues, serverValidationIssues } from "./validationIssues";
import { emailTelegramStarter } from "./builderState";

describe("workflow validation issues", () => {
    it("maps client issues to node ids", () => {
        const starter = emailTelegramStarter();
        const issues = clientValidationIssues(starter.nodes, starter.edges);
        expect(issues.some((issue) => issue.nodeId === "gmail_trigger")).toBe(true);
    });

    it("parses server node ids from backtick messages", () => {
        const issues = serverValidationIssues({
            valid: false,
            errors: ["tool node `send_draft` missing config.tool or config.tool_slug"],
            warnings: ["unreachable nodes from entry: orphan, leaf"],
            infos: [],
            external_write_nodes: [{ node_id: "send_draft", tool_slug: "gmail.send_draft" }],
        });
        expect(issues.some((issue) => issue.nodeId === "send_draft" && issue.severity === "error")).toBe(true);
        expect(issues.some((issue) => issue.nodeId === "orphan" && issue.severity === "warning")).toBe(true);
    });
});
