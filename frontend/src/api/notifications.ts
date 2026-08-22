import { apiFetch } from "./client";
import { appendCursorParams, assertCursorPage, type CursorPage, type CursorToken } from "./pagination";

export type NotificationListItem = {
    id: string;
    type: string;
    title: string;
    body_preview: string | null;
    is_read: boolean;
    created_at: string;
};

export type NotificationPreferences = {
    email_enabled: boolean;
    push_enabled: boolean;
    marketing_enabled: boolean;
};

export async function getNotificationsPage(
    options: { limit?: number; cursor?: CursorToken | null } = {},
): Promise<CursorPage<NotificationListItem>> {
    const params = new URLSearchParams();
    appendCursorParams(params, options);
    const query = params.toString();
    const payload = await apiFetch<unknown>(`/notifications${query ? `?${query}` : ""}`);
    return assertCursorPage<NotificationListItem>(payload, "/notifications");
}

export async function getNotifications(
    options: { limit?: number; cursor?: CursorToken | null } = {},
): Promise<NotificationListItem[]> {
    const page = await getNotificationsPage(options);
    return page.items;
}

export async function getUnreadNotificationsCount(): Promise<{ count: number }> {
    return apiFetch("/notifications/unread-count");
}

export async function markRead(id: string): Promise<void> {
    return apiFetch(`/notifications/${id}/read`, { method: "PATCH" });
}

export async function markAllRead(): Promise<void> {
    return apiFetch("/notifications/read-all", { method: "PATCH" });
}

export async function getPreferences(): Promise<NotificationPreferences> {
    return apiFetch("/notifications/preferences");
}

export async function updatePreferences(
    payload: Partial<NotificationPreferences>
): Promise<NotificationPreferences> {
    return apiFetch("/notifications/preferences", {
        method: "PUT",
        body: JSON.stringify(payload),
    });
}
