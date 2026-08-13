import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Alert, Box, Button, Stack, TextField, Typography } from "@mui/material";
import { Link as RouterLink, useSearchParams } from "react-router-dom";
import { resetPassword } from "../api/auth";
import { AuthMarketingPanel } from "../components/auth/AuthMarketingPanel";
import { AuthShell } from "../components/auth/AuthShell";
import { usePlatformMetadata } from "../hooks/usePlatformMetadata";

const schema = z
    .object({
        password: z.string().min(8, "At least 8 characters"),
        confirm_password: z.string(),
    })
    .refine((data) => data.password === data.confirm_password, {
        message: "Passwords do not match",
        path: ["confirm_password"],
    });

type Values = z.infer<typeof schema>;

export default function ResetPasswordPage() {
    const [searchParams] = useSearchParams();
    const token = searchParams.get("token") ?? "";
    const [done, setDone] = useState(false);
    const [serverError, setServerError] = useState("");
    const { data: platformMetadata } = usePlatformMetadata();
    const appName = platformMetadata?.app_name ?? "Troop";

    const {
        register,
        handleSubmit,
        formState: { errors, isSubmitting },
    } = useForm<Values>({ resolver: zodResolver(schema) });

    async function onSubmit(values: Values) {
        if (!token) {
            setServerError("Missing reset token. Open the link from your email again.");
            return;
        }
        setServerError("");
        try {
            await resetPassword({ token, new_password: values.password });
            setDone(true);
        } catch (error) {
            setServerError(
                error instanceof Error
                    ? error.message
                    : "Couldn't reset password. Request a new reset email from sign-in.",
            );
        }
    }

    return (
        <AuthShell
            sideContent={
                <AuthMarketingPanel
                    appName={appName}
                    eyebrow="Account recovery"
                    valueProp="Set a new password, then sign in and return to your queue."
                    points={[
                        "Use the email link once — it expires for security.",
                        "After reset, sign in with the new password.",
                    ]}
                />
            }
        >
            <Stack spacing={3}>
                <Box>
                    <Typography variant="overline" color="primary.main">
                        Reset password
                    </Typography>
                    <Typography variant="h4" component="h2" sx={{ mt: 0.5 }}>
                        {done ? "Password updated" : "Choose a new password"}
                    </Typography>
                    <Typography color="text.secondary" sx={{ mt: 1 }}>
                        {done
                            ? "Next: sign in with your new password."
                            : "At least 8 characters. Prefer a password you don't reuse elsewhere."}
                    </Typography>
                </Box>

                {done ? (
                    <Stack spacing={2}>
                        <Alert severity="success">Reset complete. You can sign in now.</Alert>
                        <Button component={RouterLink} to="/" variant="contained">
                            Sign in
                        </Button>
                    </Stack>
                ) : (
                    <Box component="form" onSubmit={handleSubmit(onSubmit)}>
                        <Stack spacing={2}>
                            {serverError && <Alert severity="error">{serverError}</Alert>}
                            {!token && (
                                <Alert severity="warning">
                                    No reset token in this URL. Use “Forgot password” on sign-in to get a fresh
                                    link.
                                </Alert>
                            )}
                            <TextField
                                label="New password"
                                type="password"
                                {...register("password")}
                                error={!!errors.password}
                                helperText={errors.password?.message}
                                fullWidth
                                autoComplete="new-password"
                            />
                            <TextField
                                label="Confirm new password"
                                type="password"
                                {...register("confirm_password")}
                                error={!!errors.confirm_password}
                                helperText={errors.confirm_password?.message}
                                fullWidth
                                autoComplete="new-password"
                            />
                            <Button type="submit" variant="contained" disabled={isSubmitting || !token}>
                                {isSubmitting ? "Saving…" : "Save new password"}
                            </Button>
                            <Button component={RouterLink} to="/" variant="text">
                                Back to sign in
                            </Button>
                        </Stack>
                    </Box>
                )}
            </Stack>
        </AuthShell>
    );
}
