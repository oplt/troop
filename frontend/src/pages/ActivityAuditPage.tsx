import { ActivityAuditContent } from "../features/activityAudit/ActivityAuditContent";
import type { MainTab } from "../features/activityAudit/hooks/useApprovals";

type ActivityAuditPageProps = {
    initialTab?: MainTab;
};

export default function ActivityAuditPage({ initialTab = "approvals" }: ActivityAuditPageProps) {
    return <ActivityAuditContent initialTab={initialTab} />;
}
