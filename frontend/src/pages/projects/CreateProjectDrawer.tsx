import { Box, Drawer, type DrawerProps } from "@mui/material";
import { useRef, type ReactNode } from "react";
import { useDrawerFocus } from "../../hooks/useDrawerFocus";

type CreateProjectDrawerProps = {
    open: boolean;
    onClose: () => void;
    children: ReactNode;
    PaperProps?: DrawerProps["PaperProps"];
};

/**
 * Right-rail create/generate project drawer shell.
 * Form body stays owned by the projects page (manual + generate modes).
 */
export function CreateProjectDrawer({ open, onClose, children, PaperProps }: CreateProjectDrawerProps) {
    const panelRef = useRef<HTMLDivElement | null>(null);
    useDrawerFocus(open, panelRef);

    return (
        <Drawer
            anchor="right"
            open={open}
            onClose={onClose}
            PaperProps={{
                sx: {
                    width: 540,
                    maxWidth: "100vw",
                    p: 3,
                    boxSizing: "border-box",
                },
                ...PaperProps,
            }}
        >
            <Box ref={panelRef}>{children}</Box>
        </Drawer>
    );
}
