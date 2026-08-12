import { useEffect, useRef, useState } from "react";
import { API_BASE, readCookie } from "../api/client";

type SseStreamOptions<T> = {
    enabled?: boolean;
    maxReconnects?: number;
    onEvent?: (event: T) => void;
    onStreamEnd?: () => void;
    onError?: () => void;
};

export type SseStreamStatus = "idle" | "connecting" | "open" | "reconnecting" | "error";

/** Parse one complete SSE block without coupling protocol handling to React state. */
export function parseSseDataBlock(block: string): string | null {
    const raw = block
        .split(/\r?\n/)
        .filter((line) => line.startsWith("data:"))
        .map((line) => line.slice(5).trim())
        .join("\n");
    return raw && raw !== "{}" ? raw : null;
}

function wait(delayMs: number, signal: AbortSignal) {
    return new Promise<boolean>((resolve) => {
        if (signal.aborted) {
            resolve(false);
            return;
        }
        const timer = window.setTimeout(() => {
            cleanup();
            resolve(true);
        }, delayMs);
        const abort = () => {
            cleanup();
            resolve(false);
        };
        const cleanup = () => {
            window.clearTimeout(timer);
            signal.removeEventListener("abort", abort);
        };
        signal.addEventListener("abort", abort, { once: true });
    });
}

export function useSseStream<T>(path: string | null, options: SseStreamOptions<T> = {}) {
    const { enabled = true, maxReconnects = 6, onEvent, onStreamEnd, onError } = options;
    const [status, setStatus] = useState<SseStreamStatus>("idle");
    const [reconnectCount, setReconnectCount] = useState(0);
    const eventRef = useRef(onEvent);
    const endRef = useRef(onStreamEnd);
    const errorRef = useRef(onError);

    useEffect(() => { eventRef.current = onEvent; }, [onEvent]);
    useEffect(() => { endRef.current = onStreamEnd; }, [onStreamEnd]);
    useEffect(() => { errorRef.current = onError; }, [onError]);

    useEffect(() => {
        if (!path || !enabled) {
            setStatus("idle");
            setReconnectCount(0);
            return;
        }

        const controller = new AbortController();
        let reconnects = 0;
        let stopped = false;
        const headers: Record<string, string> = {};
        const csrfToken = readCookie("csrf_token");
        if (csrfToken) headers["X-CSRF-Token"] = csrfToken;

        const consume = async () => {
            setStatus("connecting");
            while (!controller.signal.aborted && !stopped) {
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
                    while (!controller.signal.aborted) {
                        const { done, value } = await reader.read();
                        if (done) break;
                        receivedData = receivedData || value.byteLength > 0;
                        buffer += decoder.decode(value, { stream: true });
                        const blocks = buffer.split(/\r?\n\r?\n/);
                        buffer = blocks.pop() ?? "";
                        for (const block of blocks) {
                            const raw = parseSseDataBlock(block);
                            if (!raw || raw === "{}") continue;
                            try {
                                const parsed = JSON.parse(raw) as T & { event_type?: string };
                                if (parsed.event_type === "stream_end") {
                                    stopped = true;
                                    endRef.current?.();
                                    break;
                                }
                                eventRef.current?.(parsed);
                            } catch {
                                // Ignore malformed events and continue consuming the stream.
                            }
                        }
                        if (stopped) break;
                    }
                } catch (error) {
                    if ((error as Error).name === "AbortError") return;
                    setStatus("reconnecting");
                }
                if (stopped || controller.signal.aborted) return;
                if (receivedData) reconnects = 0;
                reconnects += 1;
                if (reconnects > maxReconnects) {
                    setStatus("error");
                    errorRef.current?.();
                    return;
                }
                setReconnectCount(reconnects);
                const shouldContinue = await wait(Math.min(1000 * 2 ** (reconnects - 1), 10000), controller.signal);
                if (!shouldContinue) return;
            }
        };

        void consume();
        return () => {
            stopped = true;
            controller.abort();
        };
    }, [enabled, maxReconnects, path]);

    return { status, reconnectCount };
}
