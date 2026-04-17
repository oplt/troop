import { useMemo } from "react";
import { useQueries, useQuery } from "@tanstack/react-query";
import { Button, Chip, Stack, Typography } from "@mui/material";
import { ArrowForward as ArrowForwardIcon } from "@mui/icons-material";
import { useNavigate } from "react-router-dom";
import { listProjects } from "../api/projects";
import {
    listOrchestrationProjects,
    listOrchestrationTasks,
    listProjectMilestones,
} from "../api/orchestration";
import { DashboardCalendar } from "../components/dashboard/DashboardCalendar";
import { PageHeader } from "../components/ui/PageHeader";
import { PageShell } from "../components/ui/PageShell";
import { usePlatformMetadata } from "../hooks/usePlatformMetadata";

export default function CalendarPage() {
    const navigate = useNavigate();
    const { data: platformMetadata } = usePlatformMetadata();
    const { data: projects, isLoading: projectsLoading } = useQuery({
        queryKey: ["projects"],
        queryFn: listProjects,
    });
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

    const orchTasksWithDue = orchestrationTasks.filter((task) => Boolean(task.due_date)).length;
    const orchMilestonesWithDue = orchestrationMilestones.filter((m) => Boolean(m.due_date)).length;

    const coreDomainPlural = platformMetadata?.core_domain_plural ?? "Projects";

    return (
        <PageShell maxWidth="xl">
            <PageHeader
                eyebrow="Planning horizon"
                title="Calendar"
                description={`Workspace items from /api/v1/calendar plus agent-project task due dates and milestones from orchestration, shown on the same grid.`}
                actions={
                    <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
                        <Button
                            variant="outlined"
                            endIcon={<ArrowForwardIcon />}
                            onClick={() => navigate("/projects")}
                        >
                            Open {coreDomainPlural}
                        </Button>
                        <Button variant="text" onClick={() => navigate("/projects?tab=agents")}>
                            Agent projects
                        </Button>
                    </Stack>
                }
                meta={
                    <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap alignItems="center">
                        <Chip
                            label={`${projects?.length ?? 0} ${coreDomainPlural.toLowerCase()}`}
                            variant="outlined"
                        />
                        <Chip
                            label={`${orchProjects.length} agent projects`}
                            variant="outlined"
                        />
                        <Typography variant="body2" color="text.secondary">
                            {orchTasksWithDue} dated tasks • {orchMilestonesWithDue} dated milestones on calendar
                        </Typography>
                    </Stack>
                }
            />

            <DashboardCalendar
                projects={projects ?? []}
                projectsLoading={projectsLoading}
                onOpenProjects={() => navigate("/projects")}
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
