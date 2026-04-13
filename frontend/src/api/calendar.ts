import { apiFetch } from "./client";
import type { ProjectTaskPriority } from "./projects";

export type CalendarItemType = "event" | "appointment" | "task";
/** `orchestration` = agent-project tasks/milestones (from API list and/or client overlay) */
export type CalendarItemSource = "planner" | "task" | "orchestration";

export type CalendarItem = {
    id: string;
    source: CalendarItemSource;
    type: CalendarItemType;
    title: string;
    description: string | null;
    date: string;
    start_time: string | null;
    end_time: string | null;
    project_id: string | null;
    project_name: string | null;
    priority: ProjectTaskPriority | null;
    /** Planner tasks use project task statuses; orchestration overlay uses orchestration task / milestone status strings */
    status: string | null;
    created_at: string;
};

export async function listCalendarItems(
    startDate: string,
    endDate: string
): Promise<CalendarItem[]> {
    const params = new URLSearchParams({
        start_date: startDate,
        end_date: endDate,
    });
    return apiFetch(`/calendar/items?${params.toString()}`);
}

export async function getCalendarItem(entryId: string): Promise<CalendarItem> {
    return apiFetch(`/calendar/items/${entryId}`);
}

export async function updateCalendarItem(
    entryId: string,
    payload: {
        title?: string;
        description?: string | null;
        date?: string;
        start_time?: string | null;
        end_time?: string | null;
    },
): Promise<CalendarItem> {
    return apiFetch(`/calendar/items/${entryId}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
    });
}

export async function deleteCalendarItem(entryId: string): Promise<void> {
    await apiFetch(`/calendar/items/${entryId}`, { method: "DELETE" });
}

export async function createCalendarItem(payload: {
    type: CalendarItemType;
    title: string;
    description?: string | null;
    date: string;
    start_time?: string | null;
    end_time?: string | null;
    project_id?: string | null;
    priority?: ProjectTaskPriority | null;
    assignee_id?: string | null;
}): Promise<CalendarItem> {
    return apiFetch("/calendar/items", {
        method: "POST",
        body: JSON.stringify(payload),
    });
}
