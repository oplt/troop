import { useEffect, useMemo, useState } from "react";
import {
    Dialog,
    DialogContent,
    DialogTitle,
    List,
    ListItemButton,
    ListItemText,
    TextField,
    Typography,
} from "@mui/material";

export type CommandPaletteRoute = {
    label: string;
    path: string;
};

type CommandPaletteProps = {
    open: boolean;
    onClose: () => void;
    routes: CommandPaletteRoute[];
    onNavigate: (path: string) => void;
};

export function CommandPalette({ open, onClose, routes, onNavigate }: CommandPaletteProps) {
    const [q, setQ] = useState("");

    useEffect(() => {
        if (open) setQ("");
    }, [open]);

    const filtered = useMemo(() => {
        const needle = q.trim().toLowerCase();
        if (!needle) return routes;
        return routes.filter(
            (r) => r.label.toLowerCase().includes(needle) || r.path.toLowerCase().includes(needle),
        );
    }, [q, routes]);

    return (
        <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
            <DialogTitle sx={{ pb: 0 }}>Go to…</DialogTitle>
            <Typography variant="caption" color="text.secondary" sx={{ px: 3, pb: 1, display: "block" }}>
                Press K (outside fields) or Ctrl / Cmd + K
            </Typography>
            <DialogContent sx={{ pt: 0 }}>
                <TextField
                    autoFocus
                    fullWidth
                    size="small"
                    placeholder="Filter pages"
                    value={q}
                    onChange={(e) => setQ(e.target.value)}
                    sx={{ mb: 1 }}
                />
                <List dense disablePadding sx={{ maxHeight: 360, overflow: "auto" }}>
                    {filtered.map((r) => (
                        <ListItemButton
                            key={r.path}
                            onClick={() => {
                                onNavigate(r.path);
                                onClose();
                            }}
                        >
                            <ListItemText primary={r.label} secondary={r.path} />
                        </ListItemButton>
                    ))}
                    {filtered.length === 0 && (
                        <Typography variant="body2" color="text.secondary" sx={{ py: 2, px: 1 }}>
                            No matches.
                        </Typography>
                    )}
                </List>
            </DialogContent>
        </Dialog>
    );
}
