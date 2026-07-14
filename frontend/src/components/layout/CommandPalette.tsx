import { useId, useMemo, useState } from "react";
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
    return (
        <CommandPaletteContent
            key={open ? "open" : "closed"}
            open={open}
            onClose={onClose}
            routes={routes}
            onNavigate={onNavigate}
        />
    );
}

function CommandPaletteContent({ open, onClose, routes, onNavigate }: CommandPaletteProps) {
    const [q, setQ] = useState("");
    const [activeIndex, setActiveIndex] = useState(0);
    const listboxId = useId();

    const filtered = useMemo(() => {
        const needle = q.trim().toLowerCase();
        if (!needle) return routes;
        return routes.filter(
            (r) => r.label.toLowerCase().includes(needle) || r.path.toLowerCase().includes(needle),
        );
    }, [q, routes]);

    const safeActiveIndex = Math.min(activeIndex, Math.max(filtered.length - 1, 0));

    function selectRoute(path: string) {
        onNavigate(path);
        onClose();
    }

    function handleListKeyDown(event: React.KeyboardEvent) {
        if (filtered.length === 0) {
            return;
        }
        if (event.key === "ArrowDown") {
            event.preventDefault();
            setActiveIndex((current) => (Math.min(current, filtered.length - 1) + 1) % filtered.length);
            return;
        }
        if (event.key === "ArrowUp") {
            event.preventDefault();
            setActiveIndex((current) => (Math.min(current, filtered.length - 1) - 1 + filtered.length) % filtered.length);
            return;
        }
        if (event.key === "Enter") {
            event.preventDefault();
            selectRoute(filtered[safeActiveIndex].path);
        }
    }

    const activeDescendantId =
        filtered.length > 0 ? `${listboxId}-option-${safeActiveIndex}` : undefined;

    return (
        <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
            <DialogTitle sx={{ pb: 0 }}>Go to…</DialogTitle>
            <Typography variant="caption" color="text.secondary" sx={{ px: 3, pb: 1, display: "block" }}>
                Press K (outside fields) or Ctrl / Cmd + K. Use arrow keys to move, Enter to open.
            </Typography>
            <DialogContent sx={{ pt: 0 }}>
                <TextField
                    autoFocus
                    fullWidth
                    size="small"
                    placeholder="Filter pages"
                    value={q}
                    onChange={(e) => setQ(e.target.value)}
                    onKeyDown={handleListKeyDown}
                    sx={{ mb: 1 }}
                />
                <List
                    dense
                    disablePadding
                    id={listboxId}
                    role="listbox"
                    aria-label="Pages"
                    aria-activedescendant={activeDescendantId}
                    onKeyDown={handleListKeyDown}
                    tabIndex={0}
                    sx={{ maxHeight: 360, overflow: "auto", outline: "none" }}
                >
                    {filtered.map((route, index) => (
                        <ListItemButton
                            key={route.path}
                            id={`${listboxId}-option-${index}`}
                            role="option"
                            aria-selected={index === safeActiveIndex}
                            selected={index === safeActiveIndex}
                            onMouseEnter={() => setActiveIndex(index)}
                            onClick={() => selectRoute(route.path)}
                        >
                            <ListItemText primary={route.label} secondary={route.path} />
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
