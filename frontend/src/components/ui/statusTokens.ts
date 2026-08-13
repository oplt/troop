import type { ChipProps } from "@mui/material";

export type StatusTone = "success" | "warning" | "error" | "info" | "default";
export type StatusKind = "run" | "task" | "approval" | "project" | "generic";

const RUN_TONES: Record<string, StatusTone> = {
    completed: "success",
    succeeded: "success",
    success: "success",
    failed: "error",
    error: "error",
    cancelled: "default",
    canceled: "default",
    in_progress: "info",
    running: "info",
    queued: "warning",
    pending: "warning",
    waiting: "warning",
    blocked: "error",
    paused: "default",
};

const TASK_TONES: Record<string, StatusTone> = {
    ...RUN_TONES,
    todo: "default",
    ready: "info",
    assigned: "info",
    in_review: "warning",
    needs_review: "warning",
    approved: "success",
    rejected: "error",
    archived: "default",
    synced_to_github: "success",
};

const APPROVAL_TONES: Record<string, StatusTone> = {
    pending: "warning",
    awaiting: "warning",
    approved: "success",
    rejected: "error",
    expired: "default",
    cancelled: "default",
};

const PROJECT_TONES: Record<string, StatusTone> = {
    active: "success",
    running: "warning",
    completed: "success",
    archived: "default",
    draft: "default",
    attention: "error",
    needs_attention: "error",
};

function toneMap(kind: StatusKind): Record<string, StatusTone> {
    if (kind === "run") return RUN_TONES;
    if (kind === "task") return TASK_TONES;
    if (kind === "approval") return APPROVAL_TONES;
    if (kind === "project") return PROJECT_TONES;
    return { ...TASK_TONES, ...APPROVAL_TONES, ...PROJECT_TONES };
}

export function resolveStatusTone(status: string, kind: StatusKind = "generic"): StatusTone {
    const key = status.trim().toLowerCase().replace(/\s+/g, "_");
    return toneMap(kind)[key] ?? "default";
}

/** MUI Chip color helper for call sites that still use raw Chip. */
export function statusChipColor(status: string, kind: StatusKind = "generic"): ChipProps["color"] {
    const tone = resolveStatusTone(status, kind);
    return tone === "default" ? "default" : tone;
}
