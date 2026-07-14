import { useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { queryKeys } from "../../../config/queryKeys";
import { useLiveSnapshotStream, type LiveSnapshotStreamOptions } from "../../../hooks/useLiveSnapshotStream";

export function useHierarchyLiveState(projectId: string | null | undefined) {
    const queryClient = useQueryClient();
    const onSnapshot = useCallback(() => {
        void Promise.all([
            queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.agents() }),
            queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.agents(projectId || "global") }),
            queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.hierarchyRuns }),
            queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.projects }),
        ]);
    }, [projectId, queryClient]);

    const options: LiveSnapshotStreamOptions = { onSnapshot };
    return useLiveSnapshotStream("/orchestration/hierarchy/stream", options);
}
