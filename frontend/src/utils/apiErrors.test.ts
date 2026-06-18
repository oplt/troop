import { describe, expect, it } from "vitest";
import { extractApiErrorMessage } from "./apiErrors";

describe("extractApiErrorMessage", () => {
    it("returns Error.message when present", () => {
        expect(extractApiErrorMessage(new Error("Network down"), "fallback")).toBe("Network down");
    });

    it("reads string detail payloads", () => {
        expect(extractApiErrorMessage({ detail: "Project not found" }, "fallback")).toBe("Project not found");
    });

    it("reads nested detail.message payloads", () => {
        expect(
            extractApiErrorMessage({ detail: { message: "Invalid token" } }, "fallback"),
        ).toBe("Invalid token");
    });

    it("falls back when detail is empty", () => {
        expect(extractApiErrorMessage({}, "Try again later")).toBe("Try again later");
    });
});
