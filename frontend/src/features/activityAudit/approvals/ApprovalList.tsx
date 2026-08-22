import { Alert, Paper, Skeleton, Stack, Tab, Tabs, Typography } from "@mui/material";

import type { ApprovalListItem } from "../../../api/orchestration";
import { SectionCard } from "../../../components/ui/SectionCard";
import { ApprovalCard } from "./ApprovalCard";

type ApprovalSubTab = "pending" | "history";

type ApprovalListProps = {
    subTab: ApprovalSubTab;
    pending: ApprovalListItem[];
    resolved: ApprovalListItem[];
    isLoading: boolean;
    queueIndex: number;
    onSubTabChange: (tab: ApprovalSubTab) => void;
    onQueueIndexChange: (index: number) => void;
};

export function ApprovalList({
    subTab,
    pending,
    resolved,
    isLoading,
    queueIndex,
    onSubTabChange,
    onQueueIndexChange,
}: ApprovalListProps) {
    return (
        <Stack spacing={2}>
            <Paper sx={{ borderRadius: 4, p: 1 }}>
                <Tabs value={subTab} onChange={(_, v) => onSubTabChange(v)}>
                    <Tab label={`Pending (${pending.length})`} value="pending" />
                    <Tab label={`History (${resolved.length})`} value="history" />
                </Tabs>
            </Paper>

            {subTab === "pending" && (
                <SectionCard
                    title="Pending approvals"
                    description="Actions that wait for a human decision before the run can continue."
                >
                    <Stack spacing={1.5}>
                        {isLoading && (
                            <Stack spacing={1.5} role="status" aria-busy="true" aria-label="Loading approvals">
                                <Skeleton variant="rounded" height={96} sx={{ borderRadius: 1 }} />
                                <Skeleton variant="rounded" height={96} sx={{ borderRadius: 1 }} />
                            </Stack>
                        )}
                        {!isLoading && pending.length === 0 && (
                            <Alert severity="success" sx={{ py: 1 }}>
                                <Typography variant="body2">
                                    All caught up — no pending approvals in this filter.
                                </Typography>
                            </Alert>
                        )}
                        {pending.map((approval, index) => (
                            <ApprovalCard
                                key={approval.id}
                                approval={approval}
                                focused={index === queueIndex}
                                onFocusCard={() => onQueueIndexChange(index)}
                            />
                        ))}
                    </Stack>
                </SectionCard>
            )}

            {subTab === "history" && (
                <SectionCard title="Approval history" description="Previously decided requests (newest first).">
                    <Stack spacing={1.5}>
                        {resolved.length === 0 && (
                            <Typography variant="body2" color="text.secondary">
                                No resolved approvals match the current filters.
                            </Typography>
                        )}
                        {resolved.map((approval) => (
                            <ApprovalCard key={approval.id} approval={approval} />
                        ))}
                    </Stack>
                </SectionCard>
            )}
        </Stack>
    );
}
