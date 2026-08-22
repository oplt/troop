import { afterEach, describe, expect, it, vi } from "vitest";

import { parseRagSseBlock, streamRagAnswer } from "./rag";

describe("RAG streaming client", () => {
    afterEach(() => vi.unstubAllGlobals());

    it("parses SSE data blocks and ignores comments", () => {
        expect(parseRagSseBlock(": keepalive")).toBeNull();
        expect(parseRagSseBlock('data: {"type":"token","text":"hello"}')).toEqual({
            type: "token",
            text: "hello",
        });
    });

    it("handles events split across response chunks", async () => {
        const encoder = new TextEncoder();
        const body = new ReadableStream<Uint8Array>({
            start(controller) {
                controller.enqueue(encoder.encode('data: {"type":"meta","query":"q","context_found":true,'));
                controller.enqueue(encoder.encode('"citations":[]}\n\ndata: {"type":"token","text":"Hi"}\n\n'));
                controller.enqueue(encoder.encode('data: {"type":"done","answer":"Hi","grounded":true,"context_found":true,"model":"m","provider":"p"}\n\n'));
                controller.close();
            },
        });
        vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(body, { status: 200 })));
        const events: unknown[] = [];

        await streamRagAnswer("project-1", { query: "q" }, {
            signal: new AbortController().signal,
            onEvent: (event) => events.push(event),
        });

        expect(events).toHaveLength(3);
        expect(events[1]).toEqual({ type: "token", text: "Hi" });
        expect(events[2]).toMatchObject({ type: "done", answer: "Hi" });
    });
});
