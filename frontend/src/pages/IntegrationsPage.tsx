import {
    Alert,
    Box,
    Button,
    Chip,
    CircularProgress,
    Dialog,
    DialogActions,
    DialogContent,
    DialogTitle,
    Divider,
    Paper,
    Skeleton,
    Stack,
    TextField,
    Typography,
} from "@mui/material";
import {
    CheckCircleOutline,
    EmailOutlined,
    LinkOutlined,
    Refresh,
    SendOutlined,
    SyncProblem,
} from "@mui/icons-material";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
    configureTelegramWebhook,
    createTelegramLink,
    disconnectGmail,
    getGmailAuthorizeUrl,
    getGmailStatus,
    getTelegramStatus,
    listTriggerSubscriptions,
    testConnectorInstallation,
    unlinkTelegram,
    type ConnectorStatus,
    type TelegramLink,
} from "../api/integrations";
import { installConnector } from "../api/workforce";
import { useSnackbar } from "../app/snackbarContext";
import { PageShell } from "../components/ui/PageShell";
import { formatDateTime, humanizeKey } from "../utils/formatters";

const integrationsKey = ["integrations"] as const;

function statusColor(status: string): "success" | "warning" | "error" | "default" {
    if (["connected", "active", "healthy", "linked"].includes(status)) return "success";
    if (["expired", "needs_reauthorization", "watch_expiring"].includes(status)) return "warning";
    if (["error", "webhook_error", "revoked"].includes(status)) return "error";
    return "default";
}

function StatusDetails({ status }: { status: ConnectorStatus }) {
    return (
        <Stack spacing={1.25}>
            <Stack direction="row" gap={1} alignItems="center" flexWrap="wrap" useFlexGap>
                <Chip
                    icon={statusColor(status.status) === "success" ? <CheckCircleOutline /> : <SyncProblem />}
                    label={humanizeKey(status.status)}
                    color={statusColor(status.status)}
                    size="small"
                />
                {status.account_label && <Typography variant="body2">{status.account_label}</Typography>}
            </Stack>
            {status.error && <Alert severity="error">{status.error}</Alert>}
            <Box>
                <Typography variant="caption" color="text.secondary">Granted scopes</Typography>
                <Stack direction="row" gap={0.75} flexWrap="wrap" useFlexGap sx={{ mt: 0.5 }}>
                    {status.granted_scopes.length
                        ? status.granted_scopes.map((scope) => <Chip key={scope} label={scope} size="small" variant="outlined" />)
                        : <Typography variant="body2" color="text.secondary">No scopes reported.</Typography>}
                </Stack>
            </Box>
            <Stack direction={{ xs: "column", sm: "row" }} gap={3}>
                <Box>
                    <Typography variant="caption" color="text.secondary">Last successful event</Typography>
                    <Typography variant="body2">
                        {status.last_successful_event_at ? formatDateTime(status.last_successful_event_at) : "Not reported"}
                    </Typography>
                </Box>
                {status.expires_at && (
                    <Box>
                        <Typography variant="caption" color="text.secondary">Authorization / watch expires</Typography>
                        <Typography variant="body2">{formatDateTime(status.expires_at)}</Typography>
                    </Box>
                )}
            </Stack>
        </Stack>
    );
}

function IntegrationCard({
    title,
    description,
    icon,
    status,
    loading,
    error,
    onConnect,
    onDisconnect,
    onTest,
    busy,
}: {
    title: string;
    description: string;
    icon: React.ReactNode;
    status?: ConnectorStatus;
    loading: boolean;
    error: unknown;
    onConnect: () => void;
    onDisconnect: () => void;
    onTest: () => void;
    busy: boolean;
}) {
    const connected = Boolean(status?.installation_id) && !["disconnected", "revoked"].includes(status?.status ?? "");
    return (
        <Paper component="section" aria-labelledby={`${title}-heading`} variant="outlined" sx={{ p: 3, borderRadius: 1, height: "100%" }}>
            <Stack spacing={2.25}>
                <Stack direction="row" gap={1.5} alignItems="center">
                    <Box sx={{ display: "grid", placeItems: "center", width: 44, height: 44, borderRadius: 1, bgcolor: "action.hover" }}>
                        {icon}
                    </Box>
                    <Box>
                        <Typography id={`${title}-heading`} variant="h6">{title}</Typography>
                        <Typography variant="body2" color="text.secondary">{description}</Typography>
                    </Box>
                </Stack>
                <Divider />
                {loading ? <Skeleton variant="rounded" height={140} /> : error ? (
                    <Alert
                        severity="warning"
                        action={<Button color="inherit" size="small" onClick={onConnect}>Configure</Button>}
                    >
                        Connection status is unavailable. The connector API may not be enabled on this server.
                    </Alert>
                ) : status ? <StatusDetails status={status} /> : null}
                <Stack direction="row" gap={1} flexWrap="wrap" useFlexGap>
                    <Button variant={connected ? "outlined" : "contained"} startIcon={<LinkOutlined />} onClick={onConnect} disabled={busy}>
                        {connected ? "Reconnect" : `Connect ${title}`}
                    </Button>
                    {connected && (
                        <>
                            <Button variant="outlined" startIcon={<Refresh />} onClick={onTest} disabled={busy}>Test connection</Button>
                            <Button color="error" onClick={onDisconnect} disabled={busy}>Disconnect</Button>
                        </>
                    )}
                    {busy && <CircularProgress size={24} aria-label="Saving connection" />}
                </Stack>
            </Stack>
        </Paper>
    );
}

export default function IntegrationsPage() {
    const queryClient = useQueryClient();
    const { showToast } = useSnackbar();
    const [telegramLink, setTelegramLink] = useState<TelegramLink | null>(null);
    const [telegramSetupOpen, setTelegramSetupOpen] = useState(false);
    const [telegramBotToken, setTelegramBotToken] = useState("");

    const gmail = useQuery({ queryKey: [...integrationsKey, "gmail"], queryFn: getGmailStatus, retry: false });
    const telegram = useQuery({ queryKey: [...integrationsKey, "telegram"], queryFn: getTelegramStatus, retry: false });
    const subscriptions = useQuery({
        queryKey: [...integrationsKey, "subscriptions"],
        queryFn: listTriggerSubscriptions,
        retry: false,
    });

    const refresh = async () => queryClient.invalidateQueries({ queryKey: integrationsKey });
    const action = useMutation({
        mutationFn: async (work: () => Promise<unknown>) => work(),
        onSuccess: async () => {
            await refresh();
            showToast({ message: "Integration updated.", severity: "success" });
        },
        onError: (error) => showToast({
            message: error instanceof Error ? error.message : "Integration action failed.",
            severity: "error",
        }),
    });

    const connectGmail = () => action.mutate(async () => {
        const { authorization_url: url } = await getGmailAuthorizeUrl();
        window.location.assign(url);
    });
    const linkTelegram = (installationId: string) => action.mutate(async () => {
        const link = await createTelegramLink(installationId);
        setTelegramLink(link);
        return link;
    });
    const connectTelegram = () => {
        const installationId = telegram.data?.installation_id;
        if (installationId) {
            linkTelegram(installationId);
        } else {
            setTelegramSetupOpen(true);
        }
    };
    const installTelegram = () => action.mutate(async () => {
        const token = telegramBotToken.trim();
        if (!token) throw new Error("Telegram bot token is required.");
        const installation = await installConnector({
            connector_slug: "telegram",
            name: "Telegram Bot",
            config_json: { bot_token: token },
        });
        await configureTelegramWebhook(installation.id);
        const link = await createTelegramLink(installation.id);
        setTelegramBotToken("");
        setTelegramSetupOpen(false);
        setTelegramLink(link);
        return link;
    });
    const test = (id: string | null) => {
        if (id) action.mutate(() => testConnectorInstallation(id));
    };

    return (
        <PageShell maxWidth="xl">
            <Stack spacing={3} sx={{ py: 3 }}>
                <Box>
                    <Typography variant="h4" gutterBottom>Integrations & connections</Typography>
                    <Typography color="text.secondary">
                        Authorize external accounts, verify health, and monitor event delivery. Credentials are never displayed.
                    </Typography>
                </Box>
                <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", lg: "repeat(2, minmax(0, 1fr))" }, gap: 2 }}>
                    <IntegrationCard
                        title="Gmail"
                        description="Read threads, create drafts, and send approved replies."
                        icon={<EmailOutlined color="primary" />}
                        status={gmail.data}
                        loading={gmail.isLoading}
                        error={gmail.error}
                        onConnect={connectGmail}
                        onTest={() => test(gmail.data?.installation_id ?? null)}
                        onDisconnect={() => gmail.data?.installation_id && action.mutate(() => disconnectGmail(gmail.data!.installation_id!))}
                        busy={action.isPending}
                    />
                    <IntegrationCard
                        title="Telegram"
                        description="Link your identity for secure workflow approvals."
                        icon={<SendOutlined color="primary" />}
                        status={telegram.data}
                        loading={telegram.isLoading}
                        error={telegram.error}
                        onConnect={connectTelegram}
                        onTest={() => test(telegram.data?.installation_id ?? null)}
                        onDisconnect={() => {
                            const bindingId = String(telegram.data?.metadata.telegram_binding_id || "");
                            if (bindingId) action.mutate(() => unlinkTelegram(bindingId));
                        }}
                        busy={action.isPending}
                    />
                </Box>
                <Paper component="section" aria-labelledby="watch-health-heading" variant="outlined" sx={{ p: 3, borderRadius: 1 }}>
                    <Stack direction="row" justifyContent="space-between" alignItems="center" gap={2}>
                        <Box>
                            <Typography id="watch-health-heading" variant="h6">Trigger subscription health</Typography>
                            <Typography variant="body2" color="text.secondary">Published Gmail watches and their latest delivery state.</Typography>
                        </Box>
                        <Button startIcon={<Refresh />} onClick={() => void subscriptions.refetch()} disabled={subscriptions.isFetching}>Refresh</Button>
                    </Stack>
                    <Divider sx={{ my: 2 }} />
                    {subscriptions.isLoading ? <Skeleton variant="rounded" height={100} /> : subscriptions.isError ? (
                        <Alert severity="warning">Trigger health is unavailable until the subscription API is enabled.</Alert>
                    ) : subscriptions.data?.length ? (
                        <Stack spacing={1}>
                            {subscriptions.data.map((item) => (
                                <Paper key={item.id} variant="outlined" sx={{ p: 1.5, borderRadius: 1 }}>
                                    <Stack direction={{ xs: "column", sm: "row" }} justifyContent="space-between" gap={1}>
                                        <Box>
                                            <Typography variant="subtitle2">{humanizeKey(item.provider)} · node {item.node_id}</Typography>
                                            <Typography variant="caption" color="text.secondary">
                                                Last event {item.last_event_at ? formatDateTime(item.last_event_at) : "not received"}
                                                {item.expires_at ? ` · expires ${formatDateTime(item.expires_at)}` : ""}
                                            </Typography>
                                            {item.error && <Alert severity="error" sx={{ mt: 1 }}>{item.error}</Alert>}
                                        </Box>
                                        <Chip label={humanizeKey(item.status)} color={statusColor(item.status)} size="small" />
                                    </Stack>
                                </Paper>
                            ))}
                        </Stack>
                    ) : <Alert severity="info">No trigger subscriptions. Publish a workflow with a Gmail trigger to create one.</Alert>}
                </Paper>
            </Stack>
            <Dialog
                open={telegramSetupOpen}
                onClose={() => setTelegramSetupOpen(false)}
                fullWidth
                maxWidth="sm"
            >
                <DialogTitle>Connect Telegram bot</DialogTitle>
                <DialogContent>
                    <Stack spacing={2} sx={{ pt: 1 }}>
                        <Alert severity="info">
                            Create a bot with BotFather, then paste its bot token. Troop encrypts it
                            and never returns it through the API.
                        </Alert>
                        <TextField
                            autoFocus
                            type="password"
                            label="Telegram bot token"
                            value={telegramBotToken}
                            onChange={(event) => setTelegramBotToken(event.target.value)}
                            autoComplete="off"
                            fullWidth
                        />
                    </Stack>
                </DialogContent>
                <DialogActions>
                    <Button onClick={() => setTelegramSetupOpen(false)}>Cancel</Button>
                    <Button
                        variant="contained"
                        disabled={!telegramBotToken.trim() || action.isPending}
                        onClick={installTelegram}
                    >
                        Connect and link
                    </Button>
                </DialogActions>
            </Dialog>
            <Dialog open={Boolean(telegramLink)} onClose={() => setTelegramLink(null)} fullWidth maxWidth="sm">
                <DialogTitle>Link Telegram</DialogTitle>
                <DialogContent>
                    <Stack spacing={2} sx={{ pt: 1 }}>
                        <Alert severity="info">This one-time link expires {telegramLink?.expires_at ? formatDateTime(telegramLink.expires_at) : "soon"}.</Alert>
                        <Button
                            component="a"
                            href={telegramLink?.deep_link_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            variant="contained"
                        >
                            Open Telegram
                        </Button>
                        <Typography variant="caption" color="text.secondary">
                            Only use this link for your own Telegram account. The token is intentionally not displayed separately.
                        </Typography>
                    </Stack>
                </DialogContent>
                <DialogActions><Button onClick={() => setTelegramLink(null)}>Done</Button></DialogActions>
            </Dialog>
        </PageShell>
    );
}
