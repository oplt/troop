import { describe, expect, it } from "vitest";
import { normalizeEmailApproval } from "./emailApproval";

describe("email approval normalization", () => {
    it("normalizes incoming and draft payload variants", () => {
        const view = normalizeEmailApproval({
            operation: "gmail.send_draft",
            email: {
                from: { name: "Customer", email: "customer@example.com" },
                subject: "Question",
                text_body: "Can you help?",
            },
            draft: {
                to: ["customer@example.com"],
                cc: "owner@example.com",
                subject: "Re: Question",
                body: "Yes.",
            },
            warnings: ["Verify delivery date"],
            risk_level: "high",
        });
        expect(view.isEmail).toBe(true);
        expect(view.incoming.from).toEqual({ name: "Customer", email: "customer@example.com" });
        expect(view.draft.cc).toEqual(["owner@example.com"]);
        expect(view.draft.body_text).toBe("Yes.");
        expect(view.warnings).toEqual(["Verify delivery date"]);
    });

    it("normalizes the canonical workflow approval payload", () => {
        const view = normalizeEmailApproval({
            action_key: "tool:gmail.send_draft",
            draft_arguments: {
                to: [{ email: "customer@example.com" }],
                subject: "Re: Question",
                body: "Canonical draft.",
            },
        });
        expect(view.isEmail).toBe(true);
        expect(view.draft.to).toEqual(["customer@example.com"]);
        expect(view.draft.body_text).toBe("Canonical draft.");
    });
});
