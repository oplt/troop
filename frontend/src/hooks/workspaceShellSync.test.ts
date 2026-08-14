import { describe, expect, it } from "vitest";

import { queryKeys } from "../config/queryKeys";
import {
    collectWorkspaceShellInvalidationKeys,
    isWorkspaceShellSnapshot,
    workspaceShellStreamHealthy,
} from "./workspaceShellSync";

describe("isWorkspaceShellSnapshot", () => {
    it("accepts valid workspace shell payloads", () => {
        expect(
            isWorkspaceShellSnapshot({ pending_approvals: 2, unread_notifications: 5 }),
        ).toBe(true);
    });

    it("rejects malformed payloads", () => {
        expect(isWorkspaceShellSnapshot({ pending_approvals: 1 })).toBe(false);
    });
});

describe("workspaceShellStreamHealthy", () => {
    it("treats open streams as healthy", () => {
        expect(workspaceShellStreamHealthy("open")).toBe(true);
    });

    it("treats reconnecting streams as unhealthy", () => {
        expect(workspaceShellStreamHealthy("reconnecting")).toBe(false);
    });
});

describe("collectWorkspaceShellInvalidationKeys", () => {
    const snapshot = { pending_approvals: 1, unread_notifications: 2 };

    it("returns no keys for the first snapshot baseline", () => {
        expect(collectWorkspaceShellInvalidationKeys(snapshot, null)).toEqual([]);
    });

    it("invalidates approval queries when pending count changes", () => {
        const keys = collectWorkspaceShellInvalidationKeys(
            { pending_approvals: 2, unread_notifications: 2 },
            snapshot,
        );
        expect(keys).toContainEqual(queryKeys.orchestration.approvalsPendingCount);
        expect(keys).toContainEqual(queryKeys.orchestration.approvals);
    });

    it("invalidates notification queries when unread count changes", () => {
        const keys = collectWorkspaceShellInvalidationKeys(
            { pending_approvals: 1, unread_notifications: 3 },
            snapshot,
        );
        expect(keys).toContainEqual(queryKeys.notifications.unreadCount);
        expect(keys).toContainEqual(queryKeys.notifications.root);
    });
});
