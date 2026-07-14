import { useEffect, useRef, useState } from "react";

import { API_BASE, readCookie } from "../api/client";

export type LiveSnapshotStreamOptions = {
    enabled?: boolean;
    maxReconnects?: number;
    coalesceMs?: number;
    /** Called with the parsed SSE `data:` payload for each snapshot event. */
    onSnapshot?: (payload: Record<string, unknown>) => void;
    onError?: () => void;
};

export type LiveSnapshotStreamStatus = "idle" | "connecting" | "open" | "reconnecting" | "error";

function waitForReconnect(delayMs: number, signal: AbortSignal): Promise<boolean> {
    if (signal.aborted) return Promise.resolve(false);
    return new Promise((resolve) => {
        const timeout = window.setTimeout(() => {
            cleanup();
            resolve(true);
        }, delayMs);
        const onAbort = () => {
            cleanup();
            resolve(false);
        };
        const cleanup = () => {
            window.clearTimeout(timeout);
            signal.removeEventListener("abort", onAbort);
        };
        signal.addEventListener("abort", onAbort, { once: true });
    });
}

export function useLiveSnapshotStream(
    path: string | null,
    options: LiveSnapshotStreamOptions = {}
) {
    const { enabled = true, maxReconnects = 6, coalesceMs = 100, onSnapshot, onError } = options;
    const [status, setStatus] = useState<LiveSnapshotStreamStatus>("idle");
    const [lastEventAt, setLastEventAt] = useState<number | null>(null);
    const [reconnectCount, setReconnectCount] = useState(0);
    const snapshotRef = useRef(onSnapshot);
    const errorRef = useRef(onError);

    useEffect(() => {
        snapshotRef.current = onSnapshot;
    }, [onSnapshot]);

    useEffect(() => {
        errorRef.current = onError;
    }, [onError]);

    useEffect(() => {
        if (!path || !enabled) {
            setStatus("idle");
            return;
        }

        const controller = new AbortController();
        let coalesceTimer: number | null = null;
        let pendingSnapshot: Record<string, unknown> | null = null;
        const csrfToken = readCookie("csrf_token");
        const headers: Record<string, string> = {};
        if (csrfToken) headers["X-CSRF-Token"] = csrfToken;

        (async () => {
            let reconnects = 0;
            setStatus("connecting");
            while (!controller.signal.aborted && reconnects <= maxReconnects) {
                let receivedData = false;
                try {
                    const response = await fetch(`${API_BASE}${path}`, {
                        credentials: "include",
                        headers,
                        signal: controller.signal,
                    });
                    if (!response.ok || !response.body) throw new Error("Live stream unavailable");
                    setStatus("open");
                    const reader = response.body.getReader();
                    const decoder = new TextDecoder();
                    let buffer = "";
                    while (true) {
                        const { done, value } = await reader.read();
                        if (done) break;
                        receivedData = receivedData || value.byteLength > 0;
                        buffer += decoder.decode(value, { stream: true });
                        const blocks = buffer.split("\n\n");
                        buffer = blocks.pop() ?? "";
                        for (const block of blocks) {
                            const line = block.trim().split("\n").find((item) => item.startsWith("data:"));
                            if (!line) continue;
                            const raw = line.slice(5).trim();
                            if (!raw || raw === "{}") continue;
                            try {
                                pendingSnapshot = JSON.parse(raw) as Record<string, unknown>;
                                if (coalesceTimer === null) {
                                    coalesceTimer = window.setTimeout(() => {
                                        coalesceTimer = null;
                                        if (!pendingSnapshot) return;
                                        const next = pendingSnapshot;
                                        pendingSnapshot = null;
                                        snapshotRef.current?.(next);
                                        setLastEventAt(Date.now());
                                    }, Math.max(0, coalesceMs));
                                }
                            } catch {
                                // ignore malformed SSE data
                            }
                        }
                    }
                } catch (error) {
                    if ((error as Error).name === "AbortError") return;
                    setStatus("reconnecting");
                }
                if (controller.signal.aborted) return;
                if (receivedData) reconnects = 0;
                reconnects += 1;
                if (reconnects > maxReconnects) {
                    setStatus("error");
                    errorRef.current?.();
                    return;
                }
                setReconnectCount(reconnects);
                const shouldReconnect = await waitForReconnect(
                    Math.min(1000 * 2 ** (reconnects - 1), 10000),
                    controller.signal
                );
                if (!shouldReconnect) return;
            }
        })();

        return () => {
            controller.abort();
            if (coalesceTimer !== null) window.clearTimeout(coalesceTimer);
            pendingSnapshot = null;
        };
    }, [coalesceMs, enabled, maxReconnects, path]);

    return { status, lastEventAt, reconnectCount };
}
