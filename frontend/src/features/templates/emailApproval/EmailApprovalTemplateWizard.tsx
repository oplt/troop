import { useMemo, useState } from "react";
import { Link as RouterLink, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
    Alert,
    Box,
    Button,
    Chip,
    FormControl,
    FormControlLabel,
    InputLabel,
    MenuItem,
    Paper,
    Radio,
    RadioGroup,
    Select,
    Stack,
    Step,
    StepLabel,
    Stepper,
    Typography,
} from "@mui/material";
import { EmailOutlined, Telegram } from "@mui/icons-material";

import { getDefaultCompany } from "../../../api/companies";
import { getGmailAuthorizeUrl, getGmailStatus, getTelegramStatus } from "../../../api/integrations";
import { bootstrapEmailApprovalTemplate, getMarketplaceCatalog } from "../../../api/workforce";
import { useSnackbar } from "../../../app/snackbarContext";
import { PageHeader } from "../../../components/ui/PageHeader";
import { PageShell } from "../../../components/ui/PageShell";
import { SectionCard } from "../../../components/ui/SectionCard";
import { extractApiErrorMessage } from "../../../utils/apiErrors";
import { queryKeys } from "../../../config/queryKeys";
import { GovernanceStepLegend } from "./GovernanceStepLegend";
import {
    EMAIL_APPROVAL_FLAGSHIP_SLUG,
    findFlagshipWorkflow,
    isEmailApprovalTemplatePack,
    isGmailConnected,
    isTelegramConnected,
    type EmailApprovalTemplatePack,
} from "./types";

const WIZARD_STEPS = ["Overview", "Connect Gmail", "Approval channel", "Install"] as const;

export function EmailApprovalTemplateWizard() {
    const navigate = useNavigate();
    const queryClient = useQueryClient();
    const { showToast } = useSnackbar();
    const [activeStep, setActiveStep] = useState(0);
    const [approvalChannel, setApprovalChannel] = useState<"in_app" | "telegram">("in_app");
    const [publishOnInstall, setPublishOnInstall] = useState(false);

    const { data: catalog } = useQuery({
        queryKey: ["workforce", "marketplace"],
        queryFn: getMarketplaceCatalog,
    });
    const { data: company } = useQuery({
        queryKey: ["companies", "default"],
        queryFn: getDefaultCompany,
    });
    const { data: gmailStatus, refetch: refetchGmail } = useQuery({
        queryKey: ["integrations", "gmail-status"],
        queryFn: getGmailStatus,
        retry: false,
    });
    const { data: telegramStatus } = useQuery({
        queryKey: ["integrations", "telegram-status"],
        queryFn: getTelegramStatus,
        retry: false,
    });

    const templatePack = useMemo<EmailApprovalTemplatePack | undefined>(() => {
        const workflow = findFlagshipWorkflow(catalog?.workflows ?? []);
        return isEmailApprovalTemplatePack(workflow?.template_pack)
            ? workflow.template_pack
            : undefined;
    }, [catalog?.workflows]);

    const gmailReady = isGmailConnected(gmailStatus?.status);
    const telegramReady = isTelegramConnected(telegramStatus?.status);
    const gmailInstallationId = gmailStatus?.installation_id ?? "";

    const installMutation = useMutation({
        mutationFn: () =>
            bootstrapEmailApprovalTemplate({
                company_id: company?.id ?? null,
                gmail_installation_id: gmailInstallationId,
                telegram_installation_id:
                    approvalChannel === "telegram" ? telegramStatus?.installation_id ?? null : null,
                approval_channel: approvalChannel,
                publish: publishOnInstall,
            }),
        onSuccess: (result) => {
            void queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.activation });
            showToast({
                message: result.published
                    ? "Email approval workflow published."
                    : "Email approval workflow installed as draft.",
                severity: "success",
            });
            navigate(`/workforce-workflows?workflow=${result.workflow_id}`);
        },
        onError: (error) =>
            showToast({
                message: extractApiErrorMessage(error, "Could not install email approval template."),
                severity: "error",
            }),
    });

    async function connectGmail() {
        const { authorization_url } = await getGmailAuthorizeUrl();
        window.location.assign(authorization_url);
    }

    function goNext() {
        setActiveStep((step) => Math.min(step + 1, WIZARD_STEPS.length - 1));
    }

    function goBack() {
        setActiveStep((step) => Math.max(step - 1, 0));
    }

    const canContinueFromGmail = gmailReady && Boolean(gmailInstallationId);
    const canContinueFromChannel =
        approvalChannel === "in_app" || (approvalChannel === "telegram" && telegramReady);

    return (
        <PageShell>
            <PageHeader
                eyebrow="Template library"
                title="Email approval automation"
                description="Guided install for the flagship Gmail triage → draft → approval → send workflow."
                actions={
                    <Button component={RouterLink} to="/marketplace" variant="outlined">
                        Browse marketplace
                    </Button>
                }
            />

            <Stepper activeStep={activeStep} alternativeLabel sx={{ mb: 3 }}>
                {WIZARD_STEPS.map((label) => (
                    <Step key={label}>
                        <StepLabel>{label}</StepLabel>
                    </Step>
                ))}
            </Stepper>

            {activeStep === 0 && templatePack ? (
                <SectionCard
                    title={templatePack.title}
                    description="What runs automatically, what is policy-gated, and what always needs a human."
                >
                    <GovernanceStepLegend pack={templatePack} />
                    <Stack direction="row" spacing={1} sx={{ mt: 2 }} flexWrap="wrap" useFlexGap>
                        <Chip size="small" label={`Slug: ${EMAIL_APPROVAL_FLAGSHIP_SLUG}`} />
                        <Chip size="small" variant="outlined" label="Gmail required" />
                        <Chip size="small" variant="outlined" label="Telegram optional" />
                    </Stack>
                    <Box sx={{ mt: 2 }}>
                        <Button variant="contained" onClick={goNext}>
                            Start setup
                        </Button>
                    </Box>
                </SectionCard>
            ) : null}

            {activeStep === 1 ? (
                <SectionCard title="Connect Gmail" description="The workflow listens for new inbox messages via your Gmail installation.">
                    <Stack spacing={2}>
                        <Paper variant="outlined" sx={{ p: 2 }}>
                            <Stack direction="row" spacing={1.5} alignItems="center">
                                <EmailOutlined color={gmailReady ? "success" : "action"} />
                                <Box sx={{ flex: 1 }}>
                                    <Typography variant="subtitle2">Gmail</Typography>
                                    <Typography variant="body2" color="text.secondary">
                                        {gmailReady
                                            ? `Connected${gmailStatus?.account_label ? ` · ${gmailStatus.account_label}` : ""}`
                                            : "Connect Gmail to receive new-message triggers."}
                                    </Typography>
                                </Box>
                                <Chip
                                    size="small"
                                    color={gmailReady ? "success" : "default"}
                                    label={gmailReady ? "Ready" : "Not connected"}
                                />
                            </Stack>
                        </Paper>
                        <Stack direction="row" spacing={1}>
                            <Button variant="contained" onClick={() => void connectGmail()}>
                                {gmailReady ? "Reconnect Gmail" : "Connect Gmail"}
                            </Button>
                            <Button variant="outlined" onClick={() => void refetchGmail()}>
                                Refresh status
                            </Button>
                            <Button component={RouterLink} to="/integrations" variant="text">
                                Integration settings
                            </Button>
                        </Stack>
                        {!canContinueFromGmail ? (
                            <Alert severity="info">Connect Gmail before continuing.</Alert>
                        ) : null}
                        <Stack direction="row" spacing={1}>
                            <Button onClick={goBack}>Back</Button>
                            <Button variant="contained" disabled={!canContinueFromGmail} onClick={goNext}>
                                Continue
                            </Button>
                        </Stack>
                    </Stack>
                </SectionCard>
            ) : null}

            {activeStep === 2 ? (
                <SectionCard
                    title="Approval channel"
                    description="External sends always require exact-effect approval. Choose where approvers get notified."
                >
                    <FormControl>
                        <RadioGroup
                            value={approvalChannel}
                            onChange={(event) =>
                                setApprovalChannel(event.target.value as "in_app" | "telegram")
                            }
                        >
                            <FormControlLabel
                                value="in_app"
                                control={<Radio />}
                                label="Troop approvals queue (recommended)"
                            />
                            <FormControlLabel
                                value="telegram"
                                control={<Radio />}
                                label="Troop + Telegram delivery"
                            />
                        </RadioGroup>
                    </FormControl>
                    {approvalChannel === "telegram" ? (
                        <Paper variant="outlined" sx={{ p: 2, mt: 2 }}>
                            <Stack direction="row" spacing={1.5} alignItems="center">
                                <Telegram color={telegramReady ? "success" : "action"} />
                                <Box sx={{ flex: 1 }}>
                                    <Typography variant="subtitle2">Telegram</Typography>
                                    <Typography variant="body2" color="text.secondary">
                                        {telegramReady
                                            ? "Linked for approval notifications."
                                            : "Link Telegram on the integrations page to enable delivery."}
                                    </Typography>
                                </Box>
                                <Button component={RouterLink} to="/integrations" size="small" variant="outlined">
                                    Open integrations
                                </Button>
                            </Stack>
                        </Paper>
                    ) : null}
                    <FormControl fullWidth sx={{ mt: 2 }} size="small">
                        <InputLabel id="publish-mode-label">Install mode</InputLabel>
                        <Select
                            labelId="publish-mode-label"
                            label="Install mode"
                            value={publishOnInstall ? "publish" : "draft"}
                            onChange={(event) => setPublishOnInstall(event.target.value === "publish")}
                        >
                            <MenuItem value="draft">Save as draft (test first)</MenuItem>
                            <MenuItem value="publish">Publish and register Gmail trigger</MenuItem>
                        </Select>
                    </FormControl>
                    <Stack direction="row" spacing={1} sx={{ mt: 2 }}>
                        <Button onClick={goBack}>Back</Button>
                        <Button variant="contained" disabled={!canContinueFromChannel} onClick={goNext}>
                            Continue
                        </Button>
                    </Stack>
                </SectionCard>
            ) : null}

            {activeStep === 3 ? (
                <SectionCard
                    title="Install template"
                    description="Creates project, task, agent, skill, and workflow wiring in one step."
                >
                    <Stack spacing={1.5}>
                        <Typography variant="body2" color="text.secondary">
                            Gmail installation: {gmailInstallationId || "missing"}
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                            Approval channel: {approvalChannel === "in_app" ? "Troop queue" : "Troop + Telegram"}
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                            Mode: {publishOnInstall ? "Publish immediately" : "Draft for testing"}
                        </Typography>
                        <Alert severity="warning">
                            Sends are blocked until a human approves the exact draft. Stale thread checks run at commit time.
                        </Alert>
                        <Stack direction="row" spacing={1}>
                            <Button onClick={goBack}>Back</Button>
                            <Button
                                variant="contained"
                                disabled={installMutation.isPending || !gmailInstallationId}
                                onClick={() => installMutation.mutate()}
                            >
                                {installMutation.isPending ? "Installing…" : "Install flagship template"}
                            </Button>
                        </Stack>
                    </Stack>
                </SectionCard>
            ) : null}
        </PageShell>
    );
}
