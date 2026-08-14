import { Button, Paper, Stack, Tab, Tabs } from "@mui/material";
import { useNavigate } from "react-router-dom";

import { DensePageMobileNotice } from "../../components/ui/DensePageMobileNotice";
import { KeyboardShortcutsMenu } from "../../components/ui/KeyboardShortcutsMenu";
import { PageHeader } from "../../components/ui/PageHeader";
import { PageShell } from "../../components/ui/PageShell";
import { ApprovalFilters } from "./approvals/ApprovalFilters";
import { ApprovalList } from "./approvals/ApprovalList";
import { HitlAuditTable } from "./audit/HitlAuditTable";
import { useApprovals } from "./hooks/useApprovals";
import { useAuditLog } from "./hooks/useAuditLog";
import { RunLedgerPanel } from "./ledger/RunLedgerPanel";

export function ActivityAuditContent() {
    const navigate = useNavigate();
    const approvals = useApprovals();
    const audit = useAuditLog({
        dateFrom: approvals.dateFrom,
        dateTo: approvals.dateTo,
        projectFilter: approvals.projectFilter,
    });

    return (
        <PageShell variant="browse">
            <PageHeader
                title="Approvals"
                description="Decide pending requests, then browse the ledger or HITL audit log. This is the action queue — not My tasks."
                actions={
                    <Stack direction="row" spacing={1} alignItems="center">
                        <KeyboardShortcutsMenu
                            title="Approvals shortcuts"
                            shortcuts={[
                                { keys: "j / k", label: "Move focus in pending queue" },
                                { keys: "a", label: "Approve focused card" },
                                { keys: "r", label: "Reject focused card" },
                            ]}
                        />
                        <Button variant="outlined" onClick={() => navigate("/my-tasks")}>
                            My tasks
                        </Button>
                    </Stack>
                }
            />
            <DensePageMobileNotice surface="Approvals queue" />

            <ApprovalFilters
                dateFrom={approvals.dateFrom}
                dateTo={approvals.dateTo}
                projectFilter={approvals.projectFilter}
                agentFilter={approvals.agentFilter}
                projects={approvals.projects}
                agents={approvals.agents}
                onDateFromChange={approvals.setDateFrom}
                onDateToChange={approvals.setDateTo}
                onProjectFilterChange={approvals.setProjectFilter}
                onAgentFilterChange={approvals.setAgentFilter}
            />

            <Paper sx={{ mb: 2, borderRadius: 4, p: 1 }}>
                <Tabs value={approvals.mainTab} onChange={(_, v) => approvals.setMainTab(v)}>
                    <Tab label="Approvals" value="approvals" />
                    <Tab label={`Run ledger (${approvals.filteredRuns.length})`} value="ledger" />
                    <Tab label={`HITL audit (${audit.filteredAuditLogs.length})`} value="audit" />
                </Tabs>
            </Paper>

            {approvals.mainTab === "approvals" && (
                <ApprovalList
                    subTab={approvals.approvalSubTab}
                    pending={approvals.pending}
                    resolved={approvals.resolved}
                    isLoading={approvals.approvalsLoading}
                    queueIndex={approvals.queueIndex}
                    onSubTabChange={approvals.setApprovalSubTab}
                    onQueueIndexChange={approvals.setQueueIndex}
                />
            )}

            {approvals.mainTab === "ledger" && (
                <RunLedgerPanel
                    runs={approvals.filteredRuns}
                    syncEvents={approvals.filteredSync}
                    projects={approvals.projects}
                    isRunsLoading={approvals.runsLoading}
                    isSyncLoading={approvals.syncLoading}
                />
            )}

            {approvals.mainTab === "audit" && (
                <HitlAuditTable logs={audit.filteredAuditLogs} isLoading={audit.isLoading} />
            )}
        </PageShell>
    );
}
