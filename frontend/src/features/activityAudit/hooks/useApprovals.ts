import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import type { Approval } from "../../../api/orchestration";
import {
    decideApproval,
    listAgents,
    listApprovals,
    listGithubSyncEvents,
    listOrchestrationProjects,
    listRuns,
} from "../../../api/orchestration";
import { useSnackbar } from "../../../app/snackbarContext";
import { queryKeys } from "../../../config/queryKeys";
import { parseDateBoundary } from "../approvalUtils";

export type MainTab = "approvals" | "ledger" | "audit";
export type ApprovalSubTab = "pending" | "history";

function parseMainTab(value: string | null): MainTab | null {
    if (value === "approvals" || value === "ledger" || value === "audit") {
        return value;
    }
    return null;
}

type UseApprovalsOptions = {
    initialTab?: MainTab;
};

export function useApprovals({ initialTab = "approvals" }: UseApprovalsOptions = {}) {
    const [searchParams, setSearchParams] = useSearchParams();
    const tabFromUrl = parseMainTab(searchParams.get("tab"));
    const resolvedInitialTab = tabFromUrl ?? initialTab;
    const queryClient = useQueryClient();
    const { showToast } = useSnackbar();
    const [mainTab, setMainTabState] = useState<MainTab>(resolvedInitialTab);
    const [approvalSubTab, setApprovalSubTab] = useState<ApprovalSubTab>("pending");
    const [dateFrom, setDateFrom] = useState("");
    const [dateTo, setDateTo] = useState("");
    const [projectFilter, setProjectFilter] = useState("");
    const [agentFilter, setAgentFilter] = useState("");
    const [queueIndex, setQueueIndex] = useState(0);

    const setMainTab = useCallback(
        (nextTab: MainTab) => {
            setMainTabState(nextTab);
            const nextParams = new URLSearchParams(searchParams);
            if (nextTab === "approvals") {
                nextParams.delete("tab");
            } else {
                nextParams.set("tab", nextTab);
            }
            setSearchParams(nextParams, { replace: true });
        },
        [searchParams, setSearchParams],
    );

    useEffect(() => {
        const nextTab = parseMainTab(searchParams.get("tab")) ?? initialTab;
        setMainTabState((current) => (current === nextTab ? current : nextTab));
    }, [searchParams, initialTab]);

    const { data: approvals = [], isLoading: approvalsLoading } = useQuery({
        queryKey: queryKeys.orchestration.approvals,
        queryFn: listApprovals,
    });
    const { data: runs = [], isLoading: runsLoading } = useQuery({
        queryKey: queryKeys.orchestration.runsRoot,
        queryFn: () => listRuns(),
    });
    const { data: projects = [] } = useQuery({
        queryKey: queryKeys.orchestration.projects,
        queryFn: listOrchestrationProjects,
    });
    const { data: agents = [] } = useQuery({
        queryKey: queryKeys.orchestration.agents(),
        queryFn: () => listAgents(),
    });
    const { data: syncEvents = [], isLoading: syncLoading } = useQuery({
        queryKey: queryKeys.orchestration.githubSyncEvents,
        queryFn: () => listGithubSyncEvents(),
    });

    const fromMs = parseDateBoundary(dateFrom, false);
    const toMs = parseDateBoundary(dateTo, true);

    const filterByDate = useCallback(
        (iso: string) => {
            const t = new Date(iso).getTime();
            if (fromMs != null && t < fromMs) return false;
            if (toMs != null && t > toMs) return false;
            return true;
        },
        [fromMs, toMs],
    );

    const filteredApprovals = useMemo(() => {
        return approvals.filter((a) => {
            if (!filterByDate(a.created_at)) return false;
            if (projectFilter && a.project_id !== projectFilter) return false;
            if (agentFilter) {
                const payloadAgent =
                    (a.payload?.agent_id as string | undefined) ||
                    (a.payload?.worker_agent_id as string | undefined) ||
                    (a.payload?.orchestrator_agent_id as string | undefined);
                const run = a.run_id ? runs.find((r) => r.id === a.run_id) : undefined;
                const runAgents = [run?.worker_agent_id, run?.orchestrator_agent_id, run?.reviewer_agent_id].filter(
                    Boolean,
                );
                const hit = payloadAgent === agentFilter || runAgents.includes(agentFilter);
                if (!hit) return false;
            }
            return true;
        });
    }, [approvals, agentFilter, projectFilter, filterByDate, runs]);

    const filteredRuns = useMemo(() => {
        return runs.filter((run) => {
            if (!filterByDate(run.created_at)) return false;
            if (projectFilter && run.project_id !== projectFilter) return false;
            if (agentFilter) {
                const ids = [run.worker_agent_id, run.orchestrator_agent_id, run.reviewer_agent_id];
                if (!ids.includes(agentFilter)) return false;
            }
            return true;
        });
    }, [runs, projectFilter, agentFilter, filterByDate]);

    const filteredSync = useMemo(() => {
        return syncEvents.filter((e) => filterByDate(e.created_at));
    }, [syncEvents, filterByDate]);

    const { pending, resolved } = useMemo(() => {
        const pendingList: Approval[] = [];
        const resolvedList: Approval[] = [];
        for (const a of filteredApprovals) {
            if (a.status === "pending") pendingList.push(a);
            else resolvedList.push(a);
        }
        pendingList.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
        resolvedList.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
        return { pending: pendingList, resolved: resolvedList };
    }, [filteredApprovals]);

    useEffect(() => {
        setQueueIndex((idx) => (pending.length === 0 ? 0 : Math.min(idx, pending.length - 1)));
    }, [pending.length]);

    const queueDecide = useMutation({
        mutationFn: ({ id, status }: { id: string; status: "approved" | "rejected" }) =>
            decideApproval(id, { status, reason: status === "rejected" ? "Rejected via keyboard shortcut" : undefined }),
        onSuccess: async (_, vars) => {
            await queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.approvals });
            showToast({
                message: vars.status === "approved" ? "Approved — next item focused." : "Rejected.",
                severity: vars.status === "approved" ? "success" : "warning",
            });
        },
        onError: (error) =>
            showToast({ message: error instanceof Error ? error.message : "Decision failed.", severity: "error" }),
    });

    useEffect(() => {
        const onKey = (event: KeyboardEvent) => {
            if (mainTab !== "approvals" || approvalSubTab !== "pending" || pending.length === 0) return;
            const target = event.target as HTMLElement | null;
            const tag = target?.tagName?.toLowerCase();
            if (tag === "input" || tag === "textarea" || target?.isContentEditable) return;
            if (event.key === "j" || event.key === "ArrowDown") {
                event.preventDefault();
                setQueueIndex((i) => Math.min(i + 1, pending.length - 1));
            } else if (event.key === "k" || event.key === "ArrowUp") {
                event.preventDefault();
                setQueueIndex((i) => Math.max(i - 1, 0));
            } else if (event.key === "a" || event.key === "A") {
                const item = pending[queueIndex];
                if (!item || queueDecide.isPending) return;
                event.preventDefault();
                queueDecide.mutate({ id: item.id, status: "approved" });
            } else if (event.key === "r" || event.key === "R") {
                const item = pending[queueIndex];
                if (!item || queueDecide.isPending) return;
                event.preventDefault();
                queueDecide.mutate({ id: item.id, status: "rejected" });
            }
        };
        window.addEventListener("keydown", onKey);
        return () => window.removeEventListener("keydown", onKey);
    }, [mainTab, approvalSubTab, pending, queueIndex, queueDecide]);

    return {
        mainTab,
        setMainTab,
        approvalSubTab,
        setApprovalSubTab,
        dateFrom,
        setDateFrom,
        dateTo,
        setDateTo,
        projectFilter,
        setProjectFilter,
        agentFilter,
        setAgentFilter,
        queueIndex,
        setQueueIndex,
        projects,
        agents,
        pending,
        resolved,
        filteredRuns,
        filteredSync,
        approvalsLoading,
        runsLoading,
        syncLoading,
    };
}
