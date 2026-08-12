import { DashboardCalendar } from "../components/dashboard/DashboardCalendar";
import { PageShell } from "../components/ui/PageShell";

export default function CalendarPage() {
    return (
        <PageShell maxWidth="xl">
            <DashboardCalendar
                allowedViews={["day", "week", "month", "twelve_month"]}
                initialView="month"
            />
        </PageShell>
    );
}
