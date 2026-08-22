import type { ReactNode } from "react";
import { Box, Divider, Drawer, IconButton, Stack, Typography } from "@mui/material";
import { Close as CloseIcon } from "@mui/icons-material";

type InspectorDrawerProps = {
    open: boolean;
    onClose: () => void;
    title: ReactNode;
    subtitle?: ReactNode;
    actions?: ReactNode;
    children: ReactNode;
    width?: number;
};

/** Shared non-destructive entity preview; full routes remain the deep-edit surface. */
export function InspectorDrawer({
    open,
    onClose,
    title,
    subtitle,
    actions,
    children,
    width = 440,
}: InspectorDrawerProps) {
    return (
        <Drawer
            anchor="right"
            open={open}
            onClose={onClose}
            PaperProps={{ sx: { width: { xs: "100%", sm: width }, maxWidth: "100%" } }}
        >
            <Stack sx={{ height: "100%" }}>
                <Stack direction="row" alignItems="flex-start" spacing={1} sx={{ p: 2 }}>
                    <Box sx={{ minWidth: 0, flex: 1 }}>
                        <Typography variant="h6" component="h2">{title}</Typography>
                        {subtitle ? (
                            <Typography variant="body2" color="text.secondary" sx={{ mt: 0.25 }}>
                                {subtitle}
                            </Typography>
                        ) : null}
                    </Box>
                    <IconButton onClick={onClose} aria-label="Close inspector">
                        <CloseIcon />
                    </IconButton>
                </Stack>
                <Divider />
                <Box sx={{ p: 2, flex: 1, overflowY: "auto" }}>{children}</Box>
                {actions ? (
                    <>
                        <Divider />
                        <Stack direction="row" justifyContent="flex-end" spacing={1} sx={{ p: 2 }}>
                            {actions}
                        </Stack>
                    </>
                ) : null}
            </Stack>
        </Drawer>
    );
}
