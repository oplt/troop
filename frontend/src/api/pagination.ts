export type CursorToken = {
    created_at: string;
    id: string;
    position?: number | null;
};

export type CursorPage<T> = {
    items: T[];
    next_cursor: CursorToken | null;
};

export function isCursorPage<T>(value: unknown): value is CursorPage<T> {
    return Boolean(
        value &&
            typeof value === "object" &&
            Array.isArray((value as CursorPage<T>).items),
    );
}

export function assertCursorPage<T>(value: unknown, endpoint: string): CursorPage<T> {
    if (!isCursorPage<T>(value)) {
        throw new Error(`Expected a cursor page from ${endpoint}, but received a non-page response.`);
    }
    return value;
}

export function appendCursorParams(
    params: URLSearchParams,
    options: { limit?: number; cursor?: CursorToken | null } = {},
): void {
    if (options.limit != null) params.set("limit", String(options.limit));
    if (options.cursor?.created_at) params.set("cursor_created_at", options.cursor.created_at);
    if (options.cursor?.id) params.set("cursor_id", options.cursor.id);
    if (options.cursor?.position != null) params.set("cursor_position", String(options.cursor.position));
}
