import { describe, expect, it } from "vitest";

import {
    EMAIL_APPROVAL_FLAGSHIP_SLUG,
    findFlagshipWorkflow,
    isGmailConnected,
} from "./types";

describe("email approval template helpers", () => {
    it("finds flagship workflow by slug or template pack", () => {
        expect(
            findFlagshipWorkflow([
                { slug: "other" },
                { slug: EMAIL_APPROVAL_FLAGSHIP_SLUG, template_pack: { flagship: true } },
            ])?.slug,
        ).toBe(EMAIL_APPROVAL_FLAGSHIP_SLUG);
    });

    it("detects connected gmail status values", () => {
        expect(isGmailConnected("connected")).toBe(true);
        expect(isGmailConnected("needs_reauthorization")).toBe(false);
    });
});
