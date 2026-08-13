import { describe, expect, it } from "vitest";
import { resolveStatusTone } from "./statusTokens";

describe("resolveStatusTone", () => {
    it("maps run statuses", () => {
        expect(resolveStatusTone("completed", "run")).toBe("success");
        expect(resolveStatusTone("failed", "run")).toBe("error");
        expect(resolveStatusTone("queued", "run")).toBe("warning");
        expect(resolveStatusTone("in_progress", "run")).toBe("info");
    });

    it("maps approval statuses", () => {
        expect(resolveStatusTone("approved", "approval")).toBe("success");
        expect(resolveStatusTone("rejected", "approval")).toBe("error");
        expect(resolveStatusTone("pending", "approval")).toBe("warning");
    });

    it("falls back to default for unknown", () => {
        expect(resolveStatusTone("mystery", "generic")).toBe("default");
    });
});
