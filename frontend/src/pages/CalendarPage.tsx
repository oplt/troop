import { useMemo } from "react";
import { useQueries, useQuery } from "@tanstack/react-query";
import {
    listOrchestrationProjects,
    listOrchestrationTasks,
    listProjectMilestones,
} from "../api/orchestration";
import { DashboardCalendar } from "../components/dashboard/DashboardCalendar";
import { PageShell } from "../components/ui/PageShell";

export default function CalendarPage() {
    const { data: orchProjects = [], isLoading: orchProjectsLoading } = useQuery({
        queryKey: ["orchestration", "projects"],
        queryFn: listOrchestrationProjects,
    });

    const taskQueries = useQueries({
        queries: orchProjects.map((project) => ({
            queryKey: ["orchestration", "project", project.id, "tasks"],
            queryFn: () => listOrchestrationTasks(project.id),
            enabled: orchProjects.length > 0,
        })),
    });
    const milestoneQueries = useQueries({
        queries: orchProjects.map((project) => ({
            queryKey: ["orchestration", "project", project.id, "milestones"],
            queryFn: () => listProjectMilestones(project.id),
            enabled: orchProjects.length > 0,
        })),
    });

    const orchestrationTasks = useMemo(
        () => taskQueries.flatMap((query) => query.data ?? []),
        [taskQueries],
    );
    const orchestrationMilestones = useMemo(
        () => milestoneQueries.flatMap((query) => query.data ?? []),
        [milestoneQueries],
    );

    return (
        <PageShell maxWidth="xl">

            <DashboardCalendar
                allowedViews={["day", "week", "month", "twelve_month"]}
                initialView="month"
                orchestrationCalendar={
                    orchProjectsLoading
                        ? undefined
                        : {
                              projects: orchProjects,
                              tasks: orchestrationTasks,
                              milestones: orchestrationMilestones,
                          }
                }
            />
        </PageShell>
    );
}
