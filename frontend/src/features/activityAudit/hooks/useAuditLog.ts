import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";

import type { HITLAuditLog } from "../../../api/orchestration";
import { listHITLAuditLogs } from "../../../api/orchestration";
import { queryKeys } from "../../../config/queryKeys";
import { parseDateBoundary } from "../approvalUtils";

type UseAuditLogOptions = {
    dateFrom: string;
    dateTo: string;
    projectFilter: string;
};

export function useAuditLog({ dateFrom, dateTo, projectFilter }: UseAuditLogOptions) {
    const { data: auditLogs = [], isLoading } = useQuery({
        queryKey: queryKeys.orchestration.hitlAuditLogs,
        queryFn: () => listHITLAuditLogs(),
    });

    const fromMs = parseDateBoundary(dateFrom, false);
    const toMs = parseDateBoundary(dateTo, true);

    const filteredAuditLogs = useMemo(() => {
        return auditLogs.filter((log: HITLAuditLog) => {
            const t = new Date(log.created_at).getTime();
            if (fromMs != null && t < fromMs) return false;
            if (toMs != null && t > toMs) return false;
            const projectId = log.metadata.project_id as string | undefined;
            return !projectFilter || projectId === projectFilter;
        });
    }, [auditLogs, fromMs, toMs, projectFilter]);

    return { filteredAuditLogs, isLoading };
}
