import { useEffect, useState } from "react";
import { Alert, Box, Button, CircularProgress, Stack, TextField, Typography } from "@mui/material";
import { Link as RouterLink, useSearchParams } from "react-router-dom";
import { resendVerification, verifyEmail } from "../api/auth";
import { AuthMarketingPanel } from "../components/auth/AuthMarketingPanel";
import { AuthShell } from "../components/auth/AuthShell";
import { usePlatformMetadata } from "../hooks/usePlatformMetadata";

export default function VerifyEmailPage() {
    const [searchParams] = useSearchParams();
    const token = searchParams.get("token");
    const [email, setEmail] = useState(searchParams.get("email") ?? "");
    const [status, setStatus] = useState<"loading" | "success" | "error" | "no-token">(
        token ? "loading" : "no-token",
    );
    const [resendDone, setResendDone] = useState(false);
    const [resending, setResending] = useState(false);
    const [resendError, setResendError] = useState("");
    const { data: platformMetadata } = usePlatformMetadata();
    const appName = platformMetadata?.app_name ?? "Troop";

    useEffect(() => {
        if (!token) {
            return;
        }
        verifyEmail({ token })
            .then(() => setStatus("success"))
            .catch(() => setStatus("error"));
    }, [token]);

    async function handleResend() {
        if (!email) {
            setResendError("Enter the email you signed up with.");
            return;
        }

        setResending(true);
        setResendError("");
        try {
            await resendVerification({ email });
            setResendDone(true);
        } catch (error) {
            setResendError(
                error instanceof Error
                    ? error.message
                    : "Couldn't send verification email. Try again in a moment.",
            );
        } finally {
            setResending(false);
        }
    }

    const statusCopy =
        status === "loading"
            ? { title: "Verifying…", detail: "Confirming your email with the link from your inbox." }
            : status === "success"
              ? { title: "Email verified", detail: "Your account is ready. Sign in to open the workspace." }
              : status === "error"
                ? {
                      title: "Link expired or invalid",
                      detail: "Request a new verification email, then open the fresh link.",
                  }
                : {
                      title: "Check your inbox",
                      detail: "Open the verification link we sent, or request another below.",
                  };

    return (
        <AuthShell
            sideContent={
                <AuthMarketingPanel
                    appName={appName}
                    eyebrow="Account trust"
                    valueProp="Verify email once so runs and approvals stay tied to a real identity."
                    points={[
                        "Valid link → you're verified and can sign in.",
                        "Expired link → resend from this page, no support ticket needed.",
                    ]}
                />
            }
        >
            <Stack spacing={3}>
                <Box>
                    <Typography variant="overline" color="primary.main">
                        Email verification
                    </Typography>
                    <Typography variant="h4" component="h2" sx={{ mt: 0.5 }}>
                        {statusCopy.title}
                    </Typography>
                    <Typography color="text.secondary" sx={{ mt: 1 }}>
                        {statusCopy.detail}
                    </Typography>
                </Box>

                {status === "loading" && (
                    <Box sx={{ display: "grid", placeItems: "center", py: 4 }} role="status" aria-live="polite">
                        <CircularProgress />
                    </Box>
                )}

                {status === "success" && (
                    <Stack spacing={2}>
                        <Alert severity="success">Verified. Next: sign in and create or open a project.</Alert>
                        <Button component={RouterLink} to="/" variant="contained">
                            Sign in
                        </Button>
                    </Stack>
                )}

                {(status === "error" || status === "no-token") && (
                    <Stack spacing={2}>
                        {status === "error" && (
                            <Alert severity="error">
                                That verification link is invalid or expired. Request a new one below.
                            </Alert>
                        )}
                        {status === "no-token" && (
                            <Alert severity="info">
                                No token in this URL. Use the email link, or resend a new message.
                            </Alert>
                        )}
                        <TextField
                            label="Email"
                            type="email"
                            value={email}
                            onChange={(event) => setEmail(event.target.value)}
                            fullWidth
                            helperText="Same address you used at sign-up."
                        />
                        {resendError && <Alert severity="error">{resendError}</Alert>}
                        {resendDone && (
                            <Alert severity="success">
                                New message sent. Check inbox (and spam), then open the new link.
                            </Alert>
                        )}
                        {!resendDone && (
                            <Button variant="contained" disabled={resending} onClick={handleResend}>
                                {resending ? "Sending…" : "Resend verification email"}
                            </Button>
                        )}
                        <Button component={RouterLink} to="/" variant="text">
                            Back to sign in
                        </Button>
                    </Stack>
                )}
            </Stack>
        </AuthShell>
    );
}
