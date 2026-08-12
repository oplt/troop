import { describe, expect, it } from "vitest";
import { parseSseDataBlock } from "./useSseStream";

describe("parseSseDataBlock", () => {
    it("joins multiline data fields", () => {
        expect(parseSseDataBlock('event: snapshot\ndata: {"id":\ndata: "run-1"}')).toBe('{"id":\n"run-1"}');
    });

    it("ignores empty heartbeat blocks", () => {
        expect(parseSseDataBlock(": keep-alive")).toBeNull();
        expect(parseSseDataBlock("data: {}\n")).toBeNull();
    });

    it("ignores non-data fields", () => {
        expect(parseSseDataBlock("id: 12\nevent: update")).toBeNull();
    });
});
