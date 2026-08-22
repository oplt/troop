import { lazy, Suspense } from "react";
import { BrowserRouter, Navigate, Route, Routes, useLocation, useParams, useSearchParams } from "react-router-dom";
import { ProtectedRoute } from "../components/guards/ProtectedRoute";
import { RouteErrorBoundary } from "../components/guards/RouteErrorBoundary";
import { AppLayout } from "../components/layout/AppLayout";
import { PageSkeleton, type PageSkeletonVariant } from "../components/ui/PageSkeleton";
import { useAuth } from "../hooks/useAuth";
import AuthHomePage from "../pages/AuthHomePage";

const DashboardPage = lazy(() => import("../pages/DashboardPage"));
const CalendarPage = lazy(() => import("../pages/CalendarPage"));
const PlatformPage = lazy(() => import("../pages/PlatformPage"));
const ProfilePage = lazy(() => import("../pages/ProfilePage"));
const ResetPasswordPage = lazy(() => import("../pages/ResetPasswordPage"));
const VerifyEmailPage = lazy(() => import("../pages/VerifyEmailPage"));
const AdminSettingsPage = lazy(() => import("../pages/AdminSettingsPage"));
const AiStudioPage = lazy(() => import("../pages/AiStudioPage"));
const AgentProfilesPage = lazy(() => import("../pages/AgentProfilesPage"));
const AgentRunDetailPage = lazy(() => import("../pages/AgentRunDetailPage"));
const HierarchyPage = lazy(() => import("../pages/HierarchyPage"));
const OrchestrationProjectsPage = lazy(() => import("../pages/OrchestrationProjectsPage.tsx"));
const OrchestrationProjectDetailPage = lazy(() => import("../pages/OrchestrationProjectDetailPage"));
const BrainstormsPage = lazy(() => import("../pages/BrainstormsPage"));
const BrainstormDetailPage = lazy(() => import("../pages/BrainstormDetailPage"));
const ActivityAuditPage = lazy(() => import("../pages/ActivityAuditPage"));
const RunInspectorPage = lazy(() => import("../pages/RunInspectorPage"));
const CostAnalyticsPage = lazy(() => import("../pages/CostAnalyticsPage"));
const ExecutionInsightsPage = lazy(() => import("../pages/ExecutionInsightsPage"));
const BenchmarkPage = lazy(() => import("../pages/BenchmarkPage"));
const SemanticMemoryPage = lazy(() => import("../pages/SemanticMemoryPage"));
const ModelSettingsPage = lazy(() => import("../pages/ModelSettingsPage"));
const OrchestrationPortfolioPage = lazy(() => import("../pages/OrchestrationPortfolioPage"));
const WorkflowTemplatesPage = lazy(() => import("../pages/WorkflowTemplatesPage"));
const CompaniesPage = lazy(() => import("../pages/CompaniesPage"));
const CompanyMemoryPage = lazy(() => import("../pages/CompanyMemoryPage"));
const NotificationsPage = lazy(() => import("../pages/NotificationsPage"));
const DepartmentsPage = lazy(() => import("../pages/DepartmentsPage"));
const SkillsPage = lazy(() => import("../pages/SkillsPage"));
const SkillBuilderPage = lazy(() => import("../features/skillBuilder/SkillBuilderPage"));
const MyTasksPage = lazy(() => import("../pages/MyTasksPage"));
const WorkforceWorkflowsPage = lazy(() => import("../pages/WorkforceWorkflowsPage"));
const MarketplacePage = lazy(() => import("../pages/MarketplacePage"));
const IntegrationsPage = lazy(() => import("../pages/IntegrationsPage"));
const EmailApprovalTemplatePage = lazy(() => import("../pages/EmailApprovalTemplatePage"));

function PageLoader({ variant = "browse" }: { variant?: PageSkeletonVariant }) {
    return <PageSkeleton variant={variant} />;
}

function SuspensePage({
    children,
    variant = "browse",
}: {
    children: React.ReactNode;
    variant?: PageSkeletonVariant;
}) {
    const location = useLocation();

    return (
        <RouteErrorBoundary resetKey={location.key}>
            <Suspense fallback={<PageLoader variant={variant} />}>{children}</Suspense>
        </RouteErrorBoundary>
    );
}

function RedirectToAdminSettingsTab({ tab }: { tab: string }) {
    const [searchParams] = useSearchParams();
    const next = new URLSearchParams(searchParams);
    next.set("tab", tab);
    return <Navigate to={`/admin/settings?${next.toString()}`} replace />;
}

function RedirectLegacyProjectPath({ suffix = "" }: { suffix?: string }) {
    const { projectId } = useParams();
    if (!projectId) {
        return <Navigate to="/projects" replace />;
    }
    return <Navigate to={`/projects/${projectId}${suffix}`} replace />;
}

export function AppRouter() {
    const { isReady, isAuthenticated, isAdmin } = useAuth();

    return (
        <BrowserRouter>
            <Routes>
                <Route path="/" element={<AuthHomePage />} />
                <Route path="/reset-password" element={<SuspensePage variant="form"><ResetPasswordPage /></SuspensePage>} />
                <Route path="/verify-email" element={<SuspensePage variant="form"><VerifyEmailPage /></SuspensePage>} />

                <Route
                    element={
                        <ProtectedRoute isReady={isReady} isAuthenticated={isAuthenticated}>
                            <AppLayout />
                        </ProtectedRoute>
                    }
                >
                    <Route path="/dashboard" element={<SuspensePage><DashboardPage /></SuspensePage>} />
                    <Route path="/calendar" element={<SuspensePage><CalendarPage /></SuspensePage>} />
                    <Route path="/platform" element={<SuspensePage><PlatformPage /></SuspensePage>} />
                    <Route path="/ai" element={<SuspensePage><AiStudioPage /></SuspensePage>} />
                    <Route path="/agents" element={<SuspensePage><AgentProfilesPage /></SuspensePage>} />
                    <Route path="/agent-runs/:runId" element={<SuspensePage variant="inspector"><AgentRunDetailPage /></SuspensePage>} />
                    <Route path="/hierarchy" element={<SuspensePage variant="canvas"><HierarchyPage /></SuspensePage>} />
                    <Route path="/hierarchy-builder" element={<Navigate to="/hierarchy" replace />} />
                    <Route path="/agent-hierarchy" element={<Navigate to="/hierarchy" replace />} />
                    <Route path="/model-settings" element={<SuspensePage><ModelSettingsPage /></SuspensePage>} />
                    <Route path="/portfolio" element={<SuspensePage><OrchestrationPortfolioPage /></SuspensePage>} />
                    <Route path="/agent-portfolio" element={<Navigate to="/portfolio" replace />} />
                    <Route path="/workflow-templates" element={<SuspensePage><WorkflowTemplatesPage /></SuspensePage>} />
                    <Route path="/templates/email-approval" element={<SuspensePage><EmailApprovalTemplatePage /></SuspensePage>} />
                    <Route path="/companies" element={<SuspensePage><CompaniesPage /></SuspensePage>} />
                    <Route path="/companies/:companyId/memory" element={<SuspensePage><CompanyMemoryPage /></SuspensePage>} />
                    <Route path="/projects" element={<SuspensePage><OrchestrationProjectsPage /></SuspensePage>} />
                    <Route path="/projects/:projectId" element={<SuspensePage variant="inspector"><OrchestrationProjectDetailPage /></SuspensePage>} />
                    <Route path="/projects/:projectId/benchmark" element={<SuspensePage><BenchmarkPage /></SuspensePage>} />
                    <Route path="/projects/:projectId/memory" element={<SuspensePage><SemanticMemoryPage /></SuspensePage>} />
                    <Route path="/agent-projects" element={<Navigate to="/projects" replace />} />
                    <Route path="/agent-projects/:projectId" element={<RedirectLegacyProjectPath />} />
                    <Route path="/work/projects" element={<Navigate to="/projects" replace />} />
                    <Route path="/skills" element={<SuspensePage><SkillsPage /></SuspensePage>} />
                    <Route path="/skills/builder" element={<SuspensePage><SkillBuilderPage /></SuspensePage>} />
                    <Route path="/skills/builder/:draftId" element={<SuspensePage><SkillBuilderPage /></SuspensePage>} />
                    <Route path="/departments" element={<SuspensePage><DepartmentsPage /></SuspensePage>} />
                    <Route path="/my-tasks" element={<SuspensePage><MyTasksPage /></SuspensePage>} />
                    <Route path="/workforce-workflows" element={<SuspensePage variant="canvas"><WorkforceWorkflowsPage /></SuspensePage>} />
                    <Route path="/marketplace" element={<SuspensePage><MarketplacePage /></SuspensePage>} />
                    <Route path="/integrations" element={<SuspensePage><IntegrationsPage /></SuspensePage>} />
                    <Route path="/github" element={<RedirectToAdminSettingsTab tab="integrations" />} />
                    <Route path="/brainstorms" element={<SuspensePage><BrainstormsPage /></SuspensePage>} />
                    <Route path="/brainstorms/:brainstormId" element={<SuspensePage><BrainstormDetailPage /></SuspensePage>} />
                    <Route path="/orchestration-settings" element={<RedirectToAdminSettingsTab tab="ai" />} />
                    <Route path="/approvals" element={<SuspensePage><ActivityAuditPage /></SuspensePage>} />
                    <Route path="/activity" element={<SuspensePage><ActivityAuditPage initialTab="ledger" /></SuspensePage>} />
                    <Route path="/audit" element={<SuspensePage><ActivityAuditPage initialTab="audit" /></SuspensePage>} />
                    <Route path="/analytics/cost" element={<SuspensePage><CostAnalyticsPage /></SuspensePage>} />
                    <Route path="/analytics/execution" element={<SuspensePage><ExecutionInsightsPage /></SuspensePage>} />
                    <Route
                        path="/agent-projects/:projectId/benchmark"
                        element={<RedirectLegacyProjectPath suffix="/benchmark" />}
                    />
                    <Route
                        path="/agent-projects/:projectId/memory"
                        element={<RedirectLegacyProjectPath suffix="/memory" />}
                    />
                    <Route path="/runs/:runId" element={<SuspensePage variant="inspector"><RunInspectorPage /></SuspensePage>} />
                    <Route path="/profile" element={<SuspensePage><ProfilePage /></SuspensePage>} />
                    <Route path="/notifications" element={<SuspensePage><NotificationsPage /></SuspensePage>} />
                    <Route
                        path="/admin/users"
                        element={
                            <ProtectedRoute
                                isReady={isReady}
                                isAuthenticated={isAuthenticated}
                                isAdmin={isAdmin}
                                requireAdmin
                            >
                                <RedirectToAdminSettingsTab tab="users" />
                            </ProtectedRoute>
                        }
                    />
                    <Route
                        path="/admin/platform"
                        element={
                            <ProtectedRoute
                                isReady={isReady}
                                isAuthenticated={isAuthenticated}
                                isAdmin={isAdmin}
                                requireAdmin
                            >
                                <RedirectToAdminSettingsTab tab="platform" />
                            </ProtectedRoute>
                        }
                    />
                    <Route
                        path="/admin/settings"
                        element={
                            <ProtectedRoute
                                isReady={isReady}
                                isAuthenticated={isAuthenticated}
                                isAdmin={isAdmin}
                                requireAdmin
                            >
                                <SuspensePage><AdminSettingsPage /></SuspensePage>
                            </ProtectedRoute>
                        }
                    />
                    <Route path="/app" element={<Navigate to="/dashboard" replace />} />
                </Route>

                <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
        </BrowserRouter>
    );
}
