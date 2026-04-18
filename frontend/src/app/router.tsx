import { lazy, Suspense } from "react";
import { BrowserRouter, Navigate, Route, Routes, useSearchParams } from "react-router-dom";
import { Box, Skeleton, Stack } from "@mui/material";
import { ProtectedRoute } from "../components/guards/ProtectedRoute";
import { AppLayout } from "../components/layout/AppLayout";
import { useAuth } from "../hooks/useAuth";
import AuthHomePage from "../pages/AuthHomePage";

const DashboardPage = lazy(() => import("../pages/DashboardPage"));
const CalendarPage = lazy(() => import("../pages/CalendarPage"));
const ProjectsPage = lazy(() => import("../pages/ProjectsPage"));
const ProjectDetailPage = lazy(() => import("../pages/ProjectDetailPage"));
const PlatformPage = lazy(() => import("../pages/PlatformPage"));
const ProfilePage = lazy(() => import("../pages/ProfilePage"));
const ResetPasswordPage = lazy(() => import("../pages/ResetPasswordPage"));
const VerifyEmailPage = lazy(() => import("../pages/VerifyEmailPage"));
const AdminUsersPage = lazy(() => import("../pages/AdminUsersPage"));
const AdminPlatformPage = lazy(() => import("../pages/AdminPlatformPage"));
const AdminSettingsPage = lazy(() => import("../pages/AdminSettingsPage"));
const AiStudioPage = lazy(() => import("../pages/AiStudioPage"));
const HierarchyPage = lazy(() => import("../pages/HierarchyPage"));
const OrchestrationProjectsPage = lazy(() => import("../pages/OrchestrationProjectsPage"));
const OrchestrationProjectDetailPage = lazy(() => import("../pages/OrchestrationProjectDetailPage"));
const BrainstormsPage = lazy(() => import("../pages/BrainstormsPage"));
const BrainstormDetailPage = lazy(() => import("../pages/BrainstormDetailPage"));
const ActivityAuditPage = lazy(() => import("../pages/ActivityAuditPage"));
const RunInspectorPage = lazy(() => import("../pages/RunInspectorPage"));
const CostAnalyticsPage = lazy(() => import("../pages/CostAnalyticsPage"));
const BenchmarkPage = lazy(() => import("../pages/BenchmarkPage"));
const SemanticMemoryPage = lazy(() => import("../pages/SemanticMemoryPage"));
const ModelSettingsPage = lazy(() => import("../pages/ModelSettingsPage"));
const OrchestrationPortfolioPage = lazy(() => import("../pages/OrchestrationPortfolioPage"));

function PageLoader() {
    return (
        <Box sx={{ px: { xs: 2, md: 3 }, py: { xs: 3, md: 4 } }}>
            <Stack spacing={3}>
                <Skeleton variant="rounded" height={170} sx={{ borderRadius: 2 }} />
                <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
                    <Skeleton variant="rounded" height={168} sx={{ borderRadius: 2, flex: 1 }} />
                    <Skeleton variant="rounded" height={168} sx={{ borderRadius: 2, flex: 1 }} />
                    <Skeleton variant="rounded" height={168} sx={{ borderRadius: 2, flex: 1 }} />
                </Stack>
                <Skeleton variant="rounded" height={260} sx={{ borderRadius: 5 }} />
            </Stack>
        </Box>
    );
}

function SuspensePage({ children }: { children: React.ReactNode }) {
    return <Suspense fallback={<PageLoader />}>{children}</Suspense>;
}

function RedirectToAdminSettingsTab({ tab }: { tab: string }) {
    const [searchParams] = useSearchParams();
    const next = new URLSearchParams(searchParams);
    next.set("tab", tab);
    return <Navigate to={`/admin/settings?${next.toString()}`} replace />;
}

export function AppRouter() {
    const { isReady, isAuthenticated, isAdmin } = useAuth();

    return (
        <BrowserRouter>
            <Routes>
                <Route path="/" element={<AuthHomePage />} />
                <Route path="/reset-password" element={<SuspensePage><ResetPasswordPage /></SuspensePage>} />
                <Route path="/verify-email" element={<SuspensePage><VerifyEmailPage /></SuspensePage>} />

                <Route
                    element={
                        <ProtectedRoute isReady={isReady} isAuthenticated={isAuthenticated}>
                            <AppLayout />
                        </ProtectedRoute>
                    }
                >
                    <Route path="/dashboard" element={<SuspensePage><DashboardPage /></SuspensePage>} />
                    <Route path="/calendar" element={<SuspensePage><CalendarPage /></SuspensePage>} />
                    <Route path="/projects" element={<SuspensePage><ProjectsPage /></SuspensePage>} />
                    <Route path="/projects/:projectId" element={<SuspensePage><ProjectDetailPage /></SuspensePage>} />
                    <Route path="/platform" element={<SuspensePage><PlatformPage /></SuspensePage>} />
                    <Route path="/ai" element={<SuspensePage><AiStudioPage /></SuspensePage>} />
                    <Route path="/hierarchy" element={<Navigate to="/hierarchy-builder" replace />} />
                    <Route path="/hierarchy-builder" element={<SuspensePage><HierarchyPage /></SuspensePage>} />
                    <Route path="/model-settings" element={<SuspensePage><ModelSettingsPage /></SuspensePage>} />
                    <Route path="/agent-portfolio" element={<SuspensePage><OrchestrationPortfolioPage /></SuspensePage>} />
                    <Route path="/agent-projects" element={<SuspensePage><OrchestrationProjectsPage /></SuspensePage>} />
                    <Route path="/agent-projects/:projectId" element={<SuspensePage><OrchestrationProjectDetailPage /></SuspensePage>} />
                    <Route path="/brainstorms" element={<SuspensePage><BrainstormsPage /></SuspensePage>} />
                    <Route path="/brainstorms/:brainstormId" element={<SuspensePage><BrainstormDetailPage /></SuspensePage>} />
                    <Route path="/github-sync" element={<RedirectToAdminSettingsTab tab="github" />} />
                    <Route path="/orchestration-settings" element={<RedirectToAdminSettingsTab tab="ai" />} />
                    <Route path="/activity" element={<SuspensePage><ActivityAuditPage /></SuspensePage>} />
                    <Route path="/analytics/cost" element={<SuspensePage><CostAnalyticsPage /></SuspensePage>} />
                    <Route path="/analytics/execution" element={<Navigate to="/dashboard" replace />} />
                    <Route path="/agent-projects/:projectId/benchmark" element={<SuspensePage><BenchmarkPage /></SuspensePage>} />
                    <Route path="/agent-projects/:projectId/memory" element={<SuspensePage><SemanticMemoryPage /></SuspensePage>} />
                    <Route path="/runs/:runId" element={<SuspensePage><RunInspectorPage /></SuspensePage>} />
                    <Route path="/profile" element={<SuspensePage><ProfilePage /></SuspensePage>} />
                    <Route path="/notifications" element={<Navigate to="/dashboard" replace />} />
                    <Route
                        path="/admin/users"
                        element={
                            <ProtectedRoute
                                isReady={isReady}
                                isAuthenticated={isAuthenticated}
                                isAdmin={isAdmin}
                                requireAdmin
                            >
                                <SuspensePage><AdminUsersPage /></SuspensePage>
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
                                <SuspensePage><AdminPlatformPage /></SuspensePage>
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
