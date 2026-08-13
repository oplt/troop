import { DashboardCalendar } from "../components/dashboard/DashboardCalendar";
import { PageShell } from "../components/ui/PageShell";
import { PageHeader } from "../components/ui/PageHeader";

export default function CalendarPage() {
    return (
        <PageShell variant="browse">
            <PageHeader
                title="Calendar"
                description="Project dates and workspace schedule."
            />
            <DashboardCalendar
                allowedViews={["day", "week", "month", "twelve_month"]}
                initialView="month"
            />
        </PageShell>
    );
}
