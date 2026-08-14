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
    Chat as ChatIcon,
    BusinessCenter,
    CalendarToday,
    CheckCircleOutline,
    CloudOutlined,
    EmailOutlined,
    GroupsOutlined,
    LinkOutlined,
    Refresh,
    SendOutlined,
    SyncProblem,
    TrackChanges,
} from "@mui/icons-material";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
    configureTelegramWebhook,
    createSlackLink,
    createTeamsLink,
    createTelegramLink,
    disconnectGmail,
    disconnectGoogleCalendar,
    disconnectGoogleDrive,
    disconnectHubSpot,
    disconnectJira,
    disconnectLinear,
    disconnectMicrosoftCalendar,
    disconnectMicrosoftDrive,
    disconnectOutlook,
    disconnectSalesforce,
    getGmailAuthorizeUrl,
    getGmailStatus,
    getGoogleCalendarAuthorizeUrl,
    getGoogleCalendarStatus,
    getGoogleDriveAuthorizeUrl,
    getGoogleDriveStatus,
    getHubSpotAuthorizeUrl,
    getHubSpotStatus,
    getJiraAuthorizeUrl,
    getJiraStatus,
    getLinearAuthorizeUrl,
    getLinearStatus,
    getMicrosoftCalendarAuthorizeUrl,
    getMicrosoftCalendarStatus,
    getMicrosoftDriveAuthorizeUrl,
    getMicrosoftDriveStatus,
    getSalesforceAuthorizeUrl,
    getSalesforceStatus,
    getOutlookAuthorizeUrl,
    getOutlookStatus,
    getSlackAuthorizeUrl,
    getSlackStatus,
    getTeamsAuthorizeUrl,
    getTeamsStatus,
    getTelegramStatus,
    listConnectorManifests,
    listTriggerSubscriptions,
    testConnectorInstallation,
    unlinkSlack,
    unlinkTeams,
    unlinkTelegram,
    type ConnectorManifest,
    type ConnectorStatus,
    type TelegramLink,
} from "../api/integrations";
import { installConnector } from "../api/workforce";
import { useSnackbar } from "../app/snackbarContext";
import { ConnectorManifestCapabilities, ConnectorScopeCapabilities } from "../features/connectors/ConnectorScopeCapabilities";
import { ConnectorSetupForm } from "../features/connectors/ConnectorSetupForm";
import { manifestForProvider } from "../features/connectors/manifestUtils";
import { PageShell } from "../components/ui/PageShell";
import { PageHeader } from "../components/ui/PageHeader";
import { formatDateTime, humanizeKey } from "../utils/formatters";
import { Link as RouterLink } from "react-router-dom";

const integrationsKey = ["integrations"] as const;

function statusColor(status: string): "success" | "warning" | "error" | "default" {
    if (["connected", "active", "healthy", "linked"].includes(status)) return "success";
    if (["expired", "needs_reauthorization", "watch_expiring"].includes(status)) return "warning";
    if (["error", "webhook_error", "revoked"].includes(status)) return "error";
    return "default";
}

function StatusDetails({
    status,
    manifest,
}: {
    status: ConnectorStatus;
    manifest?: ConnectorManifest;
}) {
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
            <ConnectorScopeCapabilities manifest={manifest} grantedScopes={status.granted_scopes} />
            {!status.granted_scopes.length && manifest ? (
                <ConnectorManifestCapabilities manifest={manifest} />
            ) : null}
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
    manifest,
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
    manifest?: ConnectorManifest;
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
                ) : status ? <StatusDetails status={status} manifest={manifest} /> : null}
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
    const [slackLink, setSlackLink] = useState<TelegramLink | null>(null);
    const [teamsLink, setTeamsLink] = useState<TelegramLink | null>(null);
    const [telegramSetupOpen, setTelegramSetupOpen] = useState(false);
    const [telegramBotToken, setTelegramBotToken] = useState("");
    const [telegramSetupConfig, setTelegramSetupConfig] = useState<Record<string, unknown>>({});

    const manifests = useQuery({ queryKey: [...integrationsKey, "manifests"], queryFn: listConnectorManifests, retry: false });
    const gmailManifest = manifestForProvider(manifests.data, "gmail");
    const outlookManifest = manifestForProvider(manifests.data, "outlook");
    const googleCalendarManifest = manifestForProvider(manifests.data, "google_calendar");
    const microsoftCalendarManifest = manifestForProvider(manifests.data, "microsoft_calendar");
    const googleDriveManifest = manifestForProvider(manifests.data, "google_drive");
    const microsoftDriveManifest = manifestForProvider(manifests.data, "microsoft_drive");
    const jiraManifest = manifestForProvider(manifests.data, "jira");
    const linearManifest = manifestForProvider(manifests.data, "linear");
    const hubspotManifest = manifestForProvider(manifests.data, "hubspot");
    const salesforceManifest = manifestForProvider(manifests.data, "salesforce");
    const telegramManifest = manifestForProvider(manifests.data, "telegram");
    const slackManifest = manifestForProvider(manifests.data, "slack");
    const teamsManifest = manifestForProvider(manifests.data, "teams");

    const gmail = useQuery({ queryKey: [...integrationsKey, "gmail"], queryFn: getGmailStatus, retry: false });
    const outlook = useQuery({ queryKey: [...integrationsKey, "outlook"], queryFn: getOutlookStatus, retry: false });
    const googleCalendar = useQuery({ queryKey: [...integrationsKey, "google_calendar"], queryFn: getGoogleCalendarStatus, retry: false });
    const microsoftCalendar = useQuery({ queryKey: [...integrationsKey, "microsoft_calendar"], queryFn: getMicrosoftCalendarStatus, retry: false });
    const googleDrive = useQuery({ queryKey: [...integrationsKey, "google_drive"], queryFn: getGoogleDriveStatus, retry: false });
    const microsoftDrive = useQuery({ queryKey: [...integrationsKey, "microsoft_drive"], queryFn: getMicrosoftDriveStatus, retry: false });
    const jira = useQuery({ queryKey: [...integrationsKey, "jira"], queryFn: getJiraStatus, retry: false });
    const linear = useQuery({ queryKey: [...integrationsKey, "linear"], queryFn: getLinearStatus, retry: false });
    const hubspot = useQuery({ queryKey: [...integrationsKey, "hubspot"], queryFn: getHubSpotStatus, retry: false });
    const salesforce = useQuery({ queryKey: [...integrationsKey, "salesforce"], queryFn: getSalesforceStatus, retry: false });
    const telegram = useQuery({ queryKey: [...integrationsKey, "telegram"], queryFn: getTelegramStatus, retry: false });
    const slack = useQuery({ queryKey: [...integrationsKey, "slack"], queryFn: getSlackStatus, retry: false });
    const teams = useQuery({ queryKey: [...integrationsKey, "teams"], queryFn: getTeamsStatus, retry: false });
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
    const connectOutlook = () => action.mutate(async () => {
        const { authorization_url: url } = await getOutlookAuthorizeUrl();
        window.location.assign(url);
    });
    const connectGoogleCalendar = () => action.mutate(async () => {
        const { authorization_url: url } = await getGoogleCalendarAuthorizeUrl();
        window.location.assign(url);
    });
    const connectMicrosoftCalendar = () => action.mutate(async () => {
        const { authorization_url: url } = await getMicrosoftCalendarAuthorizeUrl();
        window.location.assign(url);
    });
    const connectGoogleDrive = () => action.mutate(async () => {
        const { authorization_url: url } = await getGoogleDriveAuthorizeUrl();
        window.location.assign(url);
    });
    const connectMicrosoftDrive = () => action.mutate(async () => {
        const { authorization_url: url } = await getMicrosoftDriveAuthorizeUrl();
        window.location.assign(url);
    });
    const connectJira = () => action.mutate(async () => {
        const { authorization_url: url } = await getJiraAuthorizeUrl();
        window.location.assign(url);
    });
    const connectLinear = () => action.mutate(async () => {
        const { authorization_url: url } = await getLinearAuthorizeUrl();
        window.location.assign(url);
    });
    const connectHubSpot = () => action.mutate(async () => {
        const { authorization_url: url } = await getHubSpotAuthorizeUrl();
        window.location.assign(url);
    });
    const connectSalesforce = () => action.mutate(async () => {
        const { authorization_url: url } = await getSalesforceAuthorizeUrl();
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
    const connectSlack = () => action.mutate(async () => {
        const { authorization_url: url } = await getSlackAuthorizeUrl();
        window.location.assign(url);
    });
    const linkSlack = (installationId: string) => action.mutate(async () => {
        const link = await createSlackLink(installationId);
        setSlackLink(link);
        return link;
    });
    const connectTeams = () => action.mutate(async () => {
        const { authorization_url: url } = await getTeamsAuthorizeUrl();
        window.location.assign(url);
    });
    const linkTeams = (installationId: string) => action.mutate(async () => {
        const link = await createTeamsLink(installationId);
        setTeamsLink(link);
        return link;
    });
    const installTelegram = () => action.mutate(async () => {
        const token = String(telegramSetupConfig.bot_token ?? telegramBotToken).trim();
        if (!token) throw new Error("Telegram bot token is required.");
        const installation = await installConnector({
            connector_slug: "telegram",
            name: "Telegram Bot",
            config_json: { ...telegramSetupConfig, bot_token: token },
        });
        await configureTelegramWebhook(installation.id);
        const link = await createTelegramLink(installation.id);
        setTelegramBotToken("");
        setTelegramSetupConfig({});
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
                <PageHeader
                    title="Integrations"
                    description="Connect Gmail, Outlook, Telegram, Slack, Microsoft Teams, and other accounts so workflows can read and act. Credentials stay hidden."
                    actions={
                        <Button component={RouterLink} to="/marketplace" variant="outlined" size="small">
                            Marketplace connectors
                        </Button>
                    }
                />
                <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "repeat(2, minmax(0, 1fr))", xl: "repeat(4, minmax(0, 1fr))" }, gap: 2 }}>
                    <IntegrationCard
                        title="Gmail"
                        description="Read threads, create drafts, and send approved replies."
                        icon={<EmailOutlined color="primary" />}
                        status={gmail.data}
                        manifest={gmailManifest}
                        loading={gmail.isLoading}
                        error={gmail.error}
                        onConnect={connectGmail}
                        onTest={() => test(gmail.data?.installation_id ?? null)}
                        onDisconnect={() => gmail.data?.installation_id && action.mutate(() => disconnectGmail(gmail.data!.installation_id!))}
                        busy={action.isPending}
                    />
                    <IntegrationCard
                        title="Outlook Mail"
                        description="Read threads, create drafts, and send approved replies from Microsoft 365."
                        icon={<EmailOutlined color="secondary" />}
                        status={outlook.data}
                        manifest={outlookManifest}
                        loading={outlook.isLoading}
                        error={outlook.error}
                        onConnect={connectOutlook}
                        onTest={() => test(outlook.data?.installation_id ?? null)}
                        onDisconnect={() => outlook.data?.installation_id && action.mutate(() => disconnectOutlook(outlook.data!.installation_id!))}
                        busy={action.isPending}
                    />
                    <IntegrationCard
                        title="Google Calendar"
                        description="Read availability and manage approved calendar events."
                        icon={<CalendarToday color="primary" />}
                        status={googleCalendar.data}
                        manifest={googleCalendarManifest}
                        loading={googleCalendar.isLoading}
                        error={googleCalendar.error}
                        onConnect={connectGoogleCalendar}
                        onTest={() => test(googleCalendar.data?.installation_id ?? null)}
                        onDisconnect={() => googleCalendar.data?.installation_id && action.mutate(() => disconnectGoogleCalendar(googleCalendar.data!.installation_id!))}
                        busy={action.isPending}
                    />
                    <IntegrationCard
                        title="Microsoft Calendar"
                        description="Read availability and manage approved Microsoft 365 events."
                        icon={<CalendarToday color="secondary" />}
                        status={microsoftCalendar.data}
                        manifest={microsoftCalendarManifest}
                        loading={microsoftCalendar.isLoading}
                        error={microsoftCalendar.error}
                        onConnect={connectMicrosoftCalendar}
                        onTest={() => test(microsoftCalendar.data?.installation_id ?? null)}
                        onDisconnect={() => microsoftCalendar.data?.installation_id && action.mutate(() => disconnectMicrosoftCalendar(microsoftCalendar.data!.installation_id!))}
                        busy={action.isPending}
                    />
                    <IntegrationCard
                        title="Google Drive"
                        description="Sync permission-aware files into project knowledge for RAG."
                        icon={<CloudOutlined color="primary" />}
                        status={googleDrive.data}
                        manifest={googleDriveManifest}
                        loading={googleDrive.isLoading}
                        error={googleDrive.error}
                        onConnect={connectGoogleDrive}
                        onTest={() => test(googleDrive.data?.installation_id ?? null)}
                        onDisconnect={() => googleDrive.data?.installation_id && action.mutate(() => disconnectGoogleDrive(googleDrive.data!.installation_id!))}
                        busy={action.isPending}
                    />
                    <IntegrationCard
                        title="Microsoft Drive"
                        description="Sync OneDrive and SharePoint files into project knowledge for RAG."
                        icon={<CloudOutlined color="secondary" />}
                        status={microsoftDrive.data}
                        manifest={microsoftDriveManifest}
                        loading={microsoftDrive.isLoading}
                        error={microsoftDrive.error}
                        onConnect={connectMicrosoftDrive}
                        onTest={() => test(microsoftDrive.data?.installation_id ?? null)}
                        onDisconnect={() => microsoftDrive.data?.installation_id && action.mutate(() => disconnectMicrosoftDrive(microsoftDrive.data!.installation_id!))}
                        busy={action.isPending}
                    />
                    <IntegrationCard
                        title="Jira"
                        description="Search issues and manage approved Jira create, update, and comment actions."
                        icon={<TrackChanges color="primary" />}
                        status={jira.data}
                        manifest={jiraManifest}
                        loading={jira.isLoading}
                        error={jira.error}
                        onConnect={connectJira}
                        onTest={() => test(jira.data?.installation_id ?? null)}
                        onDisconnect={() => jira.data?.installation_id && action.mutate(() => disconnectJira(jira.data!.installation_id!))}
                        busy={action.isPending}
                    />
                    <IntegrationCard
                        title="Linear"
                        description="Search issues and manage approved Linear create, update, and comment actions."
                        icon={<TrackChanges color="secondary" />}
                        status={linear.data}
                        manifest={linearManifest}
                        loading={linear.isLoading}
                        error={linear.error}
                        onConnect={connectLinear}
                        onTest={() => test(linear.data?.installation_id ?? null)}
                        onDisconnect={() => linear.data?.installation_id && action.mutate(() => disconnectLinear(linear.data!.installation_id!))}
                        busy={action.isPending}
                    />
                    <IntegrationCard
                        title="HubSpot"
                        description="Search contacts and companies; approved allowlisted updates, notes, and outreach."
                        icon={<BusinessCenter color="primary" />}
                        status={hubspot.data}
                        manifest={hubspotManifest}
                        loading={hubspot.isLoading}
                        error={hubspot.error}
                        onConnect={connectHubSpot}
                        onTest={() => test(hubspot.data?.installation_id ?? null)}
                        onDisconnect={() => hubspot.data?.installation_id && action.mutate(() => disconnectHubSpot(hubspot.data!.installation_id!))}
                        busy={action.isPending}
                    />
                    <IntegrationCard
                        title="Salesforce"
                        description="Search contacts and accounts; approved allowlisted updates, tasks, and outreach."
                        icon={<BusinessCenter color="secondary" />}
                        status={salesforce.data}
                        manifest={salesforceManifest}
                        loading={salesforce.isLoading}
                        error={salesforce.error}
                        onConnect={connectSalesforce}
                        onTest={() => test(salesforce.data?.installation_id ?? null)}
                        onDisconnect={() => salesforce.data?.installation_id && action.mutate(() => disconnectSalesforce(salesforce.data!.installation_id!))}
                        busy={action.isPending}
                    />
                    <IntegrationCard
                        title="Telegram"
                        description="Link your identity for secure workflow approvals."
                        icon={<SendOutlined color="primary" />}
                        status={telegram.data}
                        manifest={telegramManifest}
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
                    <IntegrationCard
                        title="Slack"
                        description="Search threads, post messages, and receive approval decisions in Slack."
                        icon={<ChatIcon color="primary" />}
                        status={slack.data}
                        manifest={slackManifest}
                        loading={slack.isLoading}
                        error={slack.error}
                        onConnect={() => {
                            const installationId = slack.data?.installation_id;
                            if (installationId && slack.data?.status === "connected") {
                                linkSlack(installationId);
                                return;
                            }
                            connectSlack();
                        }}
                        onTest={() => test(slack.data?.installation_id ?? null)}
                        onDisconnect={() => {
                            const bindingId = String(slack.data?.metadata.slack_binding_id || "");
                            if (bindingId) action.mutate(() => unlinkSlack(bindingId));
                        }}
                        busy={action.isPending}
                    />
                    <IntegrationCard
                        title="Microsoft Teams"
                        description="Search channels, post messages, and receive approval decisions in Teams."
                        icon={<GroupsOutlined color="primary" />}
                        status={teams.data}
                        manifest={teamsManifest}
                        loading={teams.isLoading}
                        error={teams.error}
                        onConnect={() => {
                            const installationId = teams.data?.installation_id;
                            if (installationId && teams.data?.status === "connected") {
                                linkTeams(installationId);
                                return;
                            }
                            connectTeams();
                        }}
                        onTest={() => test(teams.data?.installation_id ?? null)}
                        onDisconnect={() => {
                            const bindingId = String(teams.data?.metadata.teams_binding_id || "");
                            if (bindingId) action.mutate(() => unlinkTeams(bindingId));
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
                        <ConnectorSetupForm
                            manifest={telegramManifest}
                            values={{ ...telegramSetupConfig, bot_token: telegramBotToken }}
                            onChange={(key, value) => {
                                if (key === "bot_token") {
                                    setTelegramBotToken(String(value ?? ""));
                                }
                                setTelegramSetupConfig((current) => ({ ...current, [key]: value }));
                            }}
                        />
                    </Stack>
                </DialogContent>
                <DialogActions>
                    <Button onClick={() => setTelegramSetupOpen(false)}>Cancel</Button>
                    <Button
                        variant="contained"
                        disabled={!(telegramSetupConfig.bot_token ?? telegramBotToken) || action.isPending}
                        onClick={installTelegram}
                    >
                        Connect and link
                    </Button>
                </DialogActions>
            </Dialog>
            <Dialog open={Boolean(teamsLink)} onClose={() => setTeamsLink(null)} fullWidth maxWidth="sm">
                <DialogTitle>Link Microsoft Teams identity</DialogTitle>
                <DialogContent>
                    <Stack spacing={2} sx={{ pt: 1 }}>
                        <Alert severity="info">
                            Send this message to the Troop bot in Teams before{" "}
                            {teamsLink?.expires_at ? formatDateTime(teamsLink.expires_at) : "it expires"}.
                        </Alert>
                        <TextField
                            label="Teams chat command"
                            value={teamsLink?.deep_link_url ?? ""}
                            InputProps={{ readOnly: true }}
                            fullWidth
                        />
                        <Typography variant="caption" color="text.secondary">
                            Only link your own Teams user. The command is single-use.
                        </Typography>
                    </Stack>
                </DialogContent>
                <DialogActions><Button onClick={() => setTeamsLink(null)}>Done</Button></DialogActions>
            </Dialog>
            <Dialog open={Boolean(slackLink)} onClose={() => setSlackLink(null)} fullWidth maxWidth="sm">
                <DialogTitle>Link Slack identity</DialogTitle>
                <DialogContent>
                    <Stack spacing={2} sx={{ pt: 1 }}>
                        <Alert severity="info">
                            Send this message to the Troop bot in Slack before{" "}
                            {slackLink?.expires_at ? formatDateTime(slackLink.expires_at) : "it expires"}.
                        </Alert>
                        <TextField
                            label="Slack DM command"
                            value={slackLink?.deep_link_url ?? ""}
                            InputProps={{ readOnly: true }}
                            fullWidth
                        />
                        <Typography variant="caption" color="text.secondary">
                            Only link your own Slack user. The command is single-use.
                        </Typography>
                    </Stack>
                </DialogContent>
                <DialogActions><Button onClick={() => setSlackLink(null)}>Done</Button></DialogActions>
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
