import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
    Box,
    Button,
    Chip,
    FormControlLabel,
    MenuItem,
    Stack,
    Switch,
    TextField,
    Typography,
} from "@mui/material";
import {
    MailOutline as MailOutlineIcon,
    NotificationsActive as NotificationsActiveIcon,
    Campaign as CampaignIcon,
} from "@mui/icons-material";
import { alpha } from "@mui/material/styles";
import {
    getNotifications,
    getPreferences,
    markRead,
    updatePreferences,
} from "../api/notifications";
import { EmptyState } from "../components/ui/EmptyState";
import { PageHeader } from "../components/ui/PageHeader";
import { PageShell } from "../components/ui/PageShell";
import { FilterToolbar } from "../components/ui/FilterToolbar";
import { InspectorSplit } from "../components/ui/InspectorSplit";
import { QueryState } from "../components/ui/QueryState";
import { SectionCard } from "../components/ui/SectionCard";
import { StatCard } from "../components/ui/StatCard";
import { queryKeys } from "../config/queryKeys";
import { formatDateTime, humanizeKey } from "../utils/formatters";

function PreferenceItem({
    label,
    description,
    checked,
    disabled,
    onChange,
}: {
    label: string;
    description: string;
    checked: boolean;
    disabled: boolean;
    onChange: (nextValue: boolean) => void;
}) {
    return (
        <Box
            sx={(theme) => ({
                p: 2,
                borderRadius: 4,
                border: `1px solid ${theme.palette.divider}`,
                backgroundColor: theme.palette.background.paper,
            })}
        >
            <FormControlLabel
                sx={{ alignItems: "flex-start", m: 0, width: "100%" }}
                control={
                    <Switch
                        checked={checked}
                        onChange={(event) => onChange(event.target.checked)}
                        disabled={disabled}
                    />
                }
                label={
                    <Box sx={{ ml: 1 }}>
                        <Typography variant="subtitle2">{label}</Typography>
                        <Typography variant="body2" color="text.secondary">
                            {description}
                        </Typography>
                    </Box>
                }
            />
        </Box>
    );
}

export default function NotificationsPage() {
    const queryClient = useQueryClient();
    const [search, setSearch] = useState("");
    const [readFilter, setReadFilter] = useState<"all" | "unread" | "read">("all");
    const { data: notifications, isLoading, error } = useQuery({
        queryKey: queryKeys.notifications.root,
        queryFn: getNotifications,
    });
    const { data: prefs } = useQuery({
        queryKey: queryKeys.notifications.preferences,
        queryFn: getPreferences,
    });

    const markOneMutation = useMutation({
        mutationFn: markRead,
        onSuccess: () => void queryClient.invalidateQueries({ queryKey: queryKeys.notifications.root }),
    });
    const prefsMutation = useMutation({
        mutationFn: updatePreferences,
        onSuccess: () => void queryClient.invalidateQueries({ queryKey: queryKeys.notifications.preferences }),
    });

    const unreadCount = notifications?.filter((item) => !item.is_read).length ?? 0;
    const totalCount = notifications?.length ?? 0;
    const enabledChannels = [
        prefs?.email_enabled,
        prefs?.push_enabled,
        prefs?.marketing_enabled,
    ].filter(Boolean).length;

    const filteredNotifications = useMemo(() => {
        const items = notifications ?? [];
        const q = search.trim().toLowerCase();
        return items.filter((notification) => {
            if (readFilter === "unread" && notification.is_read) return false;
            if (readFilter === "read" && !notification.is_read) return false;
            if (!q) return true;
            return [notification.title, notification.body, notification.type]
                .some((value) => String(value ?? "").toLowerCase().includes(q));
        });
    }, [notifications, readFilter, search]);

    return (
        <PageShell maxWidth="xl">
            <PageHeader
                eyebrow="Workspace"
                title="Notifications"
                description="Review recent activity and choose how Troop should reach you."
            />

            <FilterToolbar>
                <TextField
                    label="Search"
                    size="small"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder="Title or body"
                    sx={{ minWidth: { sm: 220 }, flex: 1 }}
                />
                <TextField
                    select
                    label="Read state"
                    size="small"
                    value={readFilter}
                    onChange={(e) => setReadFilter(e.target.value as "all" | "unread" | "read")}
                    sx={{ minWidth: 160 }}
                >
                    <MenuItem value="all">All</MenuItem>
                    <MenuItem value="unread">Unread</MenuItem>
                    <MenuItem value="read">Read</MenuItem>
                </TextField>
            </FilterToolbar>

            <Box
                sx={{
                    display: "grid",
                    gap: 2,
                    gridTemplateColumns: { xs: "1fr", md: "repeat(3, minmax(0, 1fr))" },
                }}
            >
                <StatCard
                    label="Unread"
                    value={unreadCount}
                    description="Fresh activity that still needs attention"
                    icon={<NotificationsActiveIcon />}
                    loading={isLoading}
                />
                <StatCard
                    label="All notifications"
                    value={totalCount}
                    description="Historical inbox items available for review"
                    icon={<MailOutlineIcon />}
                    loading={isLoading}
                    color="secondary"
                />
                <StatCard
                    label="Channels enabled"
                    value={`${enabledChannels}/3`}
                    description="Delivery routes currently turned on"
                    icon={<CampaignIcon />}
                    color="success"
                />
            </Box>

            <InspectorSplit
                hideSecondaryOnMobile={false}
                secondaryWidth={360}
                primary={
                    <SectionCard title="Inbox" description="Messages are sorted for fast scanning and clear read state.">
                        <QueryState
                            loading={isLoading}
                            error={error}
                            onRetry={() => {
                                void queryClient.invalidateQueries({ queryKey: queryKeys.notifications.root });
                            }}
                        >
                            {notifications && notifications.length > 0 ? (
                                filteredNotifications.length > 0 ? (
                                    <Stack spacing={1.5}>
                                        {filteredNotifications.map((notification) => {
                                            const isUpdatingThisItem =
                                                markOneMutation.isPending &&
                                                markOneMutation.variables === notification.id;
                                            return (
                                                <Box
                                                    key={notification.id}
                                                    sx={(theme) => ({
                                                        p: 2.25,
                                                        borderRadius: 4,
                                                        border: `1px solid ${theme.palette.divider}`,
                                                        backgroundColor: notification.is_read
                                                            ? alpha(theme.palette.background.paper, 0.68)
                                                            : alpha(theme.palette.primary.main, theme.palette.mode === "dark" ? 0.16 : 0.06),
                                                    })}
                                                >
                                                    <Stack spacing={1.25}>
                                                        <Stack
                                                            direction={{ xs: "column", sm: "row" }}
                                                            justifyContent="space-between"
                                                            spacing={1.5}
                                                        >
                                                            <Box>
                                                                <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                                                                    <Typography variant="subtitle2">{notification.title}</Typography>
                                                                    <Chip label={humanizeKey(notification.type)} size="small" variant="outlined" />
                                                                    {!notification.is_read && <Chip label="New" size="small" color="primary" />}
                                                                </Stack>
                                                            </Box>
                                                            <Typography variant="caption" color="text.secondary">
                                                                {formatDateTime(notification.created_at)}
                                                            </Typography>
                                                        </Stack>
                                                        {notification.body && (
                                                            <Typography variant="body2" color="text.secondary">
                                                                {notification.body}
                                                            </Typography>
                                                        )}
                                                        {!notification.is_read && (
                                                            <Box>
                                                                <Button
                                                                    size="small"
                                                                    variant="outlined"
                                                                    disabled={isUpdatingThisItem}
                                                                    onClick={() => markOneMutation.mutate(notification.id)}
                                                                >
                                                                    {isUpdatingThisItem ? "Saving..." : "Mark as read"}
                                                                </Button>
                                                            </Box>
                                                        )}
                                                    </Stack>
                                                </Box>
                                            );
                                        })}
                                    </Stack>
                                ) : (
                                    <Typography variant="body2" color="text.secondary">
                                        No notifications match the current filters.
                                    </Typography>
                                )
                            ) : (
                                <EmptyState
                                    icon={<NotificationsActiveIcon />}
                                    title="Inbox is clear"
                                    description="You have no notifications yet. New product updates and account events will appear here."
                                />
                            )}
                        </QueryState>
                    </SectionCard>
                }
                secondary={
                    <SectionCard title="Delivery preferences" description="Choose how you want this workspace to reach you.">
                        <Stack spacing={1.5}>
                            <PreferenceItem
                                label="Email notifications"
                                description="Receive operational updates and account messages in your inbox."
                                checked={prefs?.email_enabled ?? true}
                                disabled={prefsMutation.isPending}
                                onChange={(nextValue) => prefsMutation.mutate({ email_enabled: nextValue })}
                            />
                            <PreferenceItem
                                label="Push notifications"
                                description="Surface urgent activity directly inside the app experience."
                                checked={prefs?.push_enabled ?? true}
                                disabled={prefsMutation.isPending}
                                onChange={(nextValue) => prefsMutation.mutate({ push_enabled: nextValue })}
                            />
                            <PreferenceItem
                                label="Marketing emails"
                                description="Get launch announcements, feature roundups, and educational updates."
                                checked={prefs?.marketing_enabled ?? false}
                                disabled={prefsMutation.isPending}
                                onChange={(nextValue) => prefsMutation.mutate({ marketing_enabled: nextValue })}
                            />
                        </Stack>
                    </SectionCard>
                }
            />
        </PageShell>
    );
}
