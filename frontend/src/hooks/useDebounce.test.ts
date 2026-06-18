import { describe, expect, it } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { useDebounce } from "./useDebounce";

describe("useDebounce", () => {
    it("delays value updates", async () => {
        const { result, rerender } = renderHook(({ value }) => useDebounce(value, 100), {
            initialProps: { value: "a" },
        });
        expect(result.current).toBe("a");
        rerender({ value: "ab" });
        expect(result.current).toBe("a");
        await waitFor(() => expect(result.current).toBe("ab"), { timeout: 500 });
    });
});

describe("useCanonicalUser", () => {
    it("exports hook", async () => {
        const mod = await import("./useCanonicalUser");
        expect(typeof mod.useCanonicalUser).toBe("function");
    });
});
