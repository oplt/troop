import { useEffect, useRef } from "react";

import { API_BASE, readCookie } from "../api/client";

type UseLiveSnapshotStreamOptions = {
    enabled?: boolean;
    onSnapshot?: (payload: Record<string, unknown>) => void;
    onError?: () => void;
};

export function useLiveSnapshotStream(
    path: string | null,
    options: UseLiveSnapshotStreamOptions = {}
) {
    const { enabled = true, onSnapshot, onError } = options;
    const snapshotRef = useRef(onSnapshot);
    const errorRef = useRef(onError);

    useEffect(() => {
        snapshotRef.current = onSnapshot;
    }, [onSnapshot]);

    useEffect(() => {
        errorRef.current = onError;
    }, [onError]);

    useEffect(() => {
        if (!path || !enabled) return;

        const controller = new AbortController();
        const csrfToken = readCookie("csrf_token");
        const headers: Record<string, string> = {};
        if (csrfToken) headers["X-CSRF-Token"] = csrfToken;

        (async () => {
            try {
                const response = await fetch(`${API_BASE}${path}`, {
                    credentials: "include",
                    headers,
                    signal: controller.signal,
                });
                if (!response.ok || !response.body) {
                    errorRef.current?.();
                    return;
                }
                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                let buffer = "";
                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;
                    buffer += decoder.decode(value, { stream: true });
                    const blocks = buffer.split("\n\n");
                    buffer = blocks.pop() ?? "";
                    for (const block of blocks) {
                        const line = block.trim().split("\n").find((item) => item.startsWith("data:"));
                        if (!line) continue;
                        const raw = line.slice(5).trim();
                        if (!raw || raw === "{}") continue;
                        try {
                            snapshotRef.current?.(JSON.parse(raw) as Record<string, unknown>);
                        } catch {
                            // ignore malformed SSE data
                        }
                    }
                }
            } catch (error) {
                if ((error as Error).name !== "AbortError") {
                    errorRef.current?.();
                }
            }
        })();

        return () => controller.abort();
    }, [enabled, path]);
}
