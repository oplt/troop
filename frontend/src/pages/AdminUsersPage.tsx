import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
    Alert,
    Box,
    Chip,
    CircularProgress,
    Skeleton,
    Stack,
    Switch,
    Table,
    TableBody,
    TableCell,
    TableContainer,
    TableHead,
    TablePagination,
    TableRow,
    Tooltip,
    Typography,
} from "@mui/material";
import { PeopleAlt as PeopleAltIcon } from "@mui/icons-material";
import { listAdminUsers, updateUserStatus } from "../api/admin";
import { EmptyState } from "../components/ui/EmptyState";
import { PageShell } from "../components/ui/PageShell";
import { SectionCard } from "../components/ui/SectionCard";
import { StatCard } from "../components/ui/StatCard";
import { ResponsiveRowCard, ResponsiveTable } from "../components/ui/ResponsiveTable";
import { useDebounce } from "../hooks/useDebounce";
import { formatDate } from "../utils/formatters";

export default function AdminUsersPage() {
    const queryClient = useQueryClient();
    const [search] = useState("");
    const [page, setPage] = useState(0);
    const pageSize = 20;
    const debouncedSearch = useDebounce(search, 300);

    const { data, isLoading, error } = useQuery({
        queryKey: ["admin", "users", page, debouncedSearch],
        queryFn: () =>
            listAdminUsers({
                page: page + 1,
                page_size: pageSize,
                search: debouncedSearch || undefined,
            }),
    });
    const statusMutation = useMutation({
        mutationFn: ({ id, is_active }: { id: string; is_active: boolean }) =>
            updateUserStatus(id, { is_active }),
        onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["admin", "users"] }),
    });

    const users = data?.items ?? [];
    const activeCount = users.filter((user) => user.is_active).length;
    const verifiedCount = users.filter((user) => user.is_verified).length;
    const errorMessage = error instanceof Error ? error.message : "Couldn't load users. Refresh to retry.";

    return (
        <PageShell maxWidth="xl">

            <Box
                sx={{
                    display: "grid",
                    gap: 2,
                    gridTemplateColumns: { xs: "1fr", md: "repeat(3, minmax(0, 1fr))" },
                }}
            >
                <StatCard
                    label="Total users"
                    value={data?.total ?? 0}
                    description="Accounts matching the current search and pagination scope"
                    icon={<PeopleAltIcon />}
                    loading={isLoading}
                />
                <StatCard
                    label="Active on page"
                    value={activeCount}
                    description="Users currently allowed to access the product"
                    icon={<PeopleAltIcon />}
                    loading={isLoading}
                    color="success"
                />
                <StatCard
                    label="Verified on page"
                    value={verifiedCount}
                    description="Accounts with confirmed email identity"
                    icon={<PeopleAltIcon />}
                    loading={isLoading}
                    color="secondary"
                />
            </Box>

            {error && <Alert severity="error">{errorMessage}</Alert>}

            <SectionCard title="User directory" description="Review roles, verification, and status changes from one place.">
                {isLoading ? (
                    <Stack spacing={1.5}>
                        {Array.from({ length: 5 }).map((_, index) => (
                            <Skeleton key={index} variant="rounded" height={88} sx={{ borderRadius: 4 }} />
                        ))}
                    </Stack>
                ) : users.length === 0 ? (
                    <EmptyState
                        icon={<PeopleAltIcon />}
                        title="No users found"
                        description="Try broadening the search or check if the current filters are too narrow."
                    />
                ) : (
                    <ResponsiveTable
                        table={
                            <TableContainer>
                                <Table>
                                    <TableHead>
                                        <TableRow>
                                            <TableCell>Email</TableCell>
                                            <TableCell>Name</TableCell>
                                            <TableCell>Roles</TableCell>
                                            <TableCell>Verified</TableCell>
                                            <TableCell>Joined</TableCell>
                                            <TableCell align="center">Active</TableCell>
                                        </TableRow>
                                    </TableHead>
                                    <TableBody>
                                        {users.map((user) => {
                                            const isUpdatingThisUser =
                                                statusMutation.isPending &&
                                                statusMutation.variables?.id === user.id;
                                            return (
                                                <TableRow key={user.id} hover>
                                                    <TableCell>{user.email}</TableCell>
                                                    <TableCell>{user.full_name ?? "—"}</TableCell>
                                                    <TableCell>
                                                        <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
                                                            {user.roles.map((role) => (
                                                                <Chip key={role} label={role} size="small" />
                                                            ))}
                                                        </Stack>
                                                    </TableCell>
                                                    <TableCell>
                                                        <Chip
                                                            label={user.is_verified ? "Verified" : "Unverified"}
                                                            size="small"
                                                            color={user.is_verified ? "success" : "warning"}
                                                            variant="outlined"
                                                        />
                                                    </TableCell>
                                                    <TableCell>{formatDate(user.created_at)}</TableCell>
                                                    <TableCell align="center">
                                                        <Tooltip title={user.is_active ? "Deactivate" : "Activate"}>
                                                            <Box component="span">
                                                                {isUpdatingThisUser ? (
                                                                    <CircularProgress size={18} />
                                                                ) : (
                                                                    <Switch
                                                                        checked={user.is_active}
                                                                        size="small"
                                                                        onChange={(event) =>
                                                                            statusMutation.mutate({
                                                                                id: user.id,
                                                                                is_active: event.target.checked,
                                                                            })
                                                                        }
                                                                    />
                                                                )}
                                                            </Box>
                                                        </Tooltip>
                                                    </TableCell>
                                                </TableRow>
                                            );
                                        })}
                                    </TableBody>
                                </Table>
                            </TableContainer>
                        }
                        cards={
                            <>
                                {users.map((user) => {
                                    const isUpdatingThisUser =
                                        statusMutation.isPending &&
                                        statusMutation.variables?.id === user.id;
                                    return (
                                        <ResponsiveRowCard
                                            key={user.id}
                                            title={user.full_name ?? "Unnamed user"}
                                            meta={user.email}
                                            actions={
                                                <Switch
                                                    checked={user.is_active}
                                                    size="small"
                                                    disabled={isUpdatingThisUser}
                                                    onChange={(event) =>
                                                        statusMutation.mutate({
                                                            id: user.id,
                                                            is_active: event.target.checked,
                                                        })
                                                    }
                                                    inputProps={{ "aria-label": user.is_active ? "Deactivate user" : "Activate user" }}
                                                />
                                            }
                                        >
                                            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                                                {user.roles.map((role) => (
                                                    <Chip key={role} label={role} size="small" />
                                                ))}
                                                <Chip
                                                    label={user.is_verified ? "Verified" : "Unverified"}
                                                    size="small"
                                                    color={user.is_verified ? "success" : "warning"}
                                                    variant="outlined"
                                                />
                                            </Stack>
                                            <Typography variant="caption" color="text.secondary">
                                                Joined {formatDate(user.created_at)}
                                            </Typography>
                                        </ResponsiveRowCard>
                                    );
                                })}
                            </>
                        }
                    />
                )}

                <TablePagination
                    component="div"
                    count={data?.total ?? 0}
                    page={page}
                    rowsPerPage={pageSize}
                    rowsPerPageOptions={[pageSize]}
                    onPageChange={(_, nextPage) => setPage(nextPage)}
                />
            </SectionCard>
        </PageShell>
    );
}
