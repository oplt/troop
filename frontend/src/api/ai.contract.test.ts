import { afterEach, describe, expect, it, vi } from "vitest";

import {
    createAiDatasetCaseFromTrace,
    createAiRun,
    getAiRun,
    listAiRuns,
    updateAiDataset,
} from "./ai";

function jsonResponse(payload: unknown) {
    return new Response(JSON.stringify(payload), {
        status: 200,
        headers: { "Content-Type": "application/json" },
    });
}

describe("AI API contract", () => {
    afterEach(() => vi.unstubAllGlobals());

    it("exposes run list, detail, and async creation endpoints", async () => {
        const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(jsonResponse({ items: [], next_cursor: null })));
        vi.stubGlobal("fetch", fetchMock);

        await listAiRuns();
        await getAiRun("run/id");
        await createAiRun({ variables: {}, document_ids: [], top_k: 0, review_required: false }, true);

        expect(fetchMock.mock.calls[0][0]).toMatch(/\/ai\/runs$/);
        expect(fetchMock.mock.calls[1][0]).toMatch(/\/ai\/runs\/run%2Fid$/);
        expect(fetchMock.mock.calls[2][0]).toMatch(/\/ai\/runs\?queue_async=true$/);
    });

    it("updates datasets and creates cases from orchestration traces", async () => {
        const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(jsonResponse({})));
        vi.stubGlobal("fetch", fetchMock);

        await updateAiDataset("dataset-1", { name: "Production failures" });
        await createAiDatasetCaseFromTrace("dataset-1", {
            run_id: "run-1",
            source_trace_span_id: "span-1",
            expected_assertions: { mode: "deterministic", rules: [] },
        });

        expect(fetchMock.mock.calls[0][0]).toMatch(/\/ai\/evaluation-datasets\/dataset-1$/);
        expect(fetchMock.mock.calls[0][1]).toMatchObject({ method: "PATCH" });
        expect(fetchMock.mock.calls[1][0]).toMatch(/\/cases\/from-trace$/);
        expect(JSON.parse(String(fetchMock.mock.calls[1][1]?.body))).toMatchObject({
            run_id: "run-1",
            source_trace_span_id: "span-1",
        });
    });
});
