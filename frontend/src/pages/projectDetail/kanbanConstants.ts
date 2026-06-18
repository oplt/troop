export const MAIN_KANBAN_COLUMNS: {
    status: string;
    statuses: string[];
    label: string;
    color: "default" | "warning" | "info" | "success" | "error";
}[] = [
    { status: "backlog", statuses: ["backlog"], label: "Backlog", color: "default" },
    { status: "queued", statuses: ["queued", "planned"], label: "Ready", color: "warning" },
    { status: "in_progress", statuses: ["in_progress"], label: "In progress", color: "info" },
    { status: "needs_review", statuses: ["needs_review", "approved"], label: "Review", color: "warning" },
    { status: "completed", statuses: ["completed", "synced_to_github"], label: "Done", color: "success" },
];
