import { useEffect, useRef } from "react";
import { useQueryClient, type QueryClient, type QueryKey } from "@tanstack/react-query";

import { queryKeys } from "../config/queryKeys";
import { useLiveSnapshotStream, type LiveSnapshotStreamStatus } from "./useLiveSnapshotStream";

export type WorkspaceShellSnapshot = {
    pending_approvals: number;
    unread_notifications: number;
};

export const WORKSPACE_SHELL_STREAM_PATH = "/orchestration/workspace/stream";

/** Fallback polling when the workspace SSE stream is unhealthy. */
export const WORKSPACE_SHELL_FALLBACK_POLL_MS = {
    approvals: 120_000,
    notifications: 180_000,
} as const;

export function isWorkspaceShellSnapshot(payload: Record<string, unknown>): payload is WorkspaceShellSnapshot {
    return (
        typeof payload.pending_approvals === "number" &&
        typeof payload.unread_notifications === "number"
    );
}

export function workspaceShellStreamHealthy(status: LiveSnapshotStreamStatus): boolean {
    return status === "open";
}

/** Returns query keys to invalidate when shell badge counts change. */
export function collectWorkspaceShellInvalidationKeys(
    snapshot: WorkspaceShellSnapshot,
    previous: WorkspaceShellSnapshot | null,
): QueryKey[] {
    if (!previous) {
        return [];
    }
    const keys: QueryKey[] = [];
    if (snapshot.pending_approvals !== previous.pending_approvals) {
        keys.push(queryKeys.orchestration.approvalsPendingCount);
        keys.push(queryKeys.orchestration.approvals);
    }
    if (snapshot.unread_notifications !== previous.unread_notifications) {
        keys.push(queryKeys.notifications.unreadCount);
        keys.push(queryKeys.notifications.root);
    }
    return keys;
}

export function applyWorkspaceShellSnapshotSync(
    queryClient: QueryClient,
    payload: Record<string, unknown>,
    previousRef: { current: WorkspaceShellSnapshot | null },
): void {
    if (!isWorkspaceShellSnapshot(payload)) {
        return;
    }
    const keys = collectWorkspaceShellInvalidationKeys(payload, previousRef.current);
    for (const queryKey of keys) {
        void queryClient.invalidateQueries({ queryKey });
    }
    previousRef.current = payload;
}

export function useWorkspaceShellStream(enabled: boolean) {
    const queryClient = useQueryClient();
    const previousRef = useRef<WorkspaceShellSnapshot | null>(null);

    useEffect(() => {
        if (!enabled) {
            previousRef.current = null;
        }
    }, [enabled]);

    return useLiveSnapshotStream(enabled ? WORKSPACE_SHELL_STREAM_PATH : null, {
        enabled,
        coalesceMs: 150,
        onSnapshot: (payload) => {
            applyWorkspaceShellSnapshotSync(queryClient, payload, previousRef);
        },
    });
}
