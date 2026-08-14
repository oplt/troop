import { useId, useState } from "react";
import { IconButton, ListItemText, Menu, MenuItem, Tooltip, Typography } from "@mui/material";
import { Keyboard as KeyboardIcon } from "@mui/icons-material";

export type KeyboardShortcutItem = {
    keys: string;
    label: string;
};

type KeyboardShortcutsMenuProps = {
    title?: string;
    shortcuts: KeyboardShortcutItem[];
    /** Accessible name for the trigger. */
    ariaLabel?: string;
};

/**
 * Discoverable one-click keyboard map for power-user surfaces.
 */
export function KeyboardShortcutsMenu({
    title = "Keyboard",
    shortcuts,
    ariaLabel = "Keyboard shortcuts",
}: KeyboardShortcutsMenuProps) {
    const menuId = useId();
    const [anchorEl, setAnchorEl] = useState<HTMLElement | null>(null);
    const open = Boolean(anchorEl);

    return (
        <>
            <Tooltip title={title}>
                <IconButton
                    size="small"
                    aria-label={ariaLabel}
                    aria-controls={open ? menuId : undefined}
                    aria-haspopup="true"
                    aria-expanded={open ? "true" : undefined}
                    onClick={(event) => setAnchorEl(event.currentTarget)}
                >
                    <KeyboardIcon fontSize="small" />
                </IconButton>
            </Tooltip>
            <Menu
                id={menuId}
                anchorEl={anchorEl}
                open={open}
                onClose={() => setAnchorEl(null)}
                anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
                transformOrigin={{ vertical: "top", horizontal: "right" }}
            >
                <MenuItem disabled sx={{ opacity: 1 }}>
                    <Typography variant="subtitle2">{title}</Typography>
                </MenuItem>
                {shortcuts.map((item) => (
                    <MenuItem key={`${item.keys}-${item.label}`} dense disabled sx={{ opacity: 1 }}>
                        <ListItemText
                            primary={item.label}
                            secondary={item.keys}
                            primaryTypographyProps={{ variant: "body2" }}
                            secondaryTypographyProps={{
                                variant: "caption",
                                sx: { fontFamily: "monospace" },
                            }}
                        />
                    </MenuItem>
                ))}
            </Menu>
        </>
    );
}
