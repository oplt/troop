import { useQuery } from "@tanstack/react-query";

import { getPendingApprovalsCount } from "../api/orchestration";
import { getUnreadNotificationsCount } from "../api/notifications";
import { queryKeys } from "../config/queryKeys";
import { queryPolicies } from "../config/queryPolicies";
import {
    useWorkspaceShellStream,
    WORKSPACE_SHELL_FALLBACK_POLL_MS,
    workspaceShellStreamHealthy,
} from "./workspaceShellSync";

type UseNavBadgesOptions = {
    enabled?: boolean;
};

export function useNavBadges(options: UseNavBadgesOptions = {}) {
    const { enabled = true } = options;
    const stream = useWorkspaceShellStream(enabled);
    const streamHealthy = workspaceShellStreamHealthy(stream.status);

    const { data: pendingApprovals } = useQuery({
        queryKey: queryKeys.orchestration.approvalsPendingCount,
        queryFn: getPendingApprovalsCount,
        ...queryPolicies.operational,
        refetchInterval: enabled && !streamHealthy ? WORKSPACE_SHELL_FALLBACK_POLL_MS.approvals : false,
        enabled,
        retry: false,
    });

    const { data: unreadNotifications } = useQuery({
        queryKey: queryKeys.notifications.unreadCount,
        queryFn: getUnreadNotificationsCount,
        ...queryPolicies.operational,
        refetchInterval: enabled && !streamHealthy ? WORKSPACE_SHELL_FALLBACK_POLL_MS.notifications : false,
        enabled,
        retry: false,
    });

    return {
        pendingCount: pendingApprovals?.count ?? 0,
        unreadNotifications: unreadNotifications?.count ?? 0,
        streamStatus: stream.status,
        streamHealthy,
    };
}
