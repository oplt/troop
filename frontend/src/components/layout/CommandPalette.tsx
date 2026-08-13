import { useId, useMemo, useRef, useState } from "react";
import {
    Box,
    Dialog,
    DialogContent,
    DialogTitle,
    List,
    ListItemButton,
    ListItemText,
    TextField,
    Typography,
} from "@mui/material";
import { commandShortcutLabel } from "./recentProjects";

export type CommandPaletteItem = {
    id: string;
    label: string;
    path: string;
    group: "suggested" | "recent" | "actions" | "pages";
    secondary?: string;
};

type CommandPaletteProps = {
    open: boolean;
    onClose: () => void;
    items: CommandPaletteItem[];
    onNavigate: (path: string) => void;
};

const GROUP_ORDER: CommandPaletteItem["group"][] = ["suggested", "recent", "actions", "pages"];
const GROUP_LABEL: Record<CommandPaletteItem["group"], string> = {
    suggested: "Suggested",
    recent: "Recent projects",
    actions: "Actions",
    pages: "Pages",
};

export function CommandPalette({ open, onClose, items, onNavigate }: CommandPaletteProps) {
    return (
        <CommandPaletteContent
            key={open ? "open" : "closed"}
            open={open}
            onClose={onClose}
            items={items}
            onNavigate={onNavigate}
        />
    );
}

function CommandPaletteContent({ open, onClose, items, onNavigate }: CommandPaletteProps) {
    const [q, setQ] = useState("");
    const [activeIndex, setActiveIndex] = useState(0);
    const listboxId = useId();
    const inputId = useId();
    const inputRef = useRef<HTMLInputElement>(null);
    const shortcut = commandShortcutLabel();

    const filtered = useMemo(() => {
        const needle = q.trim().toLowerCase();
        const runMatch = needle.match(/^(?:run\s+)?([0-9a-f-]{8,})$/i);
        const dynamic: CommandPaletteItem[] = [];
        if (runMatch) {
            const runId = runMatch[1];
            dynamic.push({
                id: `run-${runId}`,
                label: `Open run ${runId.slice(0, 8)}…`,
                path: `/runs/${runId}`,
                group: "actions",
                secondary: `/runs/${runId}`,
            });
        }
        const base = !needle
            ? items
            : items.filter(
                  (item) =>
                      item.label.toLowerCase().includes(needle) ||
                      item.path.toLowerCase().includes(needle) ||
                      (item.secondary?.toLowerCase().includes(needle) ?? false),
              );
        const merged = [...dynamic, ...base];
        const seen = new Set<string>();
        return merged.filter((item) => {
            if (seen.has(item.id)) {
                return false;
            }
            seen.add(item.id);
            return true;
        });
    }, [q, items]);

    const grouped = useMemo(() => {
        return GROUP_ORDER.map((group) => ({
            group,
            items: filtered.filter((item) => item.group === group),
        })).filter((section) => section.items.length > 0);
    }, [filtered]);

    const flat = useMemo(() => grouped.flatMap((section) => section.items), [grouped]);
    const safeActiveIndex = Math.min(activeIndex, Math.max(flat.length - 1, 0));

    function selectItem(item: CommandPaletteItem) {
        onNavigate(item.path);
        onClose();
    }

    function handleListKeyDown(event: React.KeyboardEvent) {
        if (flat.length === 0) {
            return;
        }
        if (event.key === "ArrowDown") {
            event.preventDefault();
            setActiveIndex((current) => (Math.min(current, flat.length - 1) + 1) % flat.length);
            return;
        }
        if (event.key === "ArrowUp") {
            event.preventDefault();
            setActiveIndex(
                (current) => (Math.min(current, flat.length - 1) - 1 + flat.length) % flat.length,
            );
            return;
        }
        if (event.key === "Enter") {
            event.preventDefault();
            selectItem(flat[safeActiveIndex]);
        }
    }

    const activeDescendantId =
        flat.length > 0 ? `${listboxId}-option-${flat[safeActiveIndex].id}` : undefined;

    return (
        <Dialog
            open={open}
            onClose={onClose}
            fullWidth
            maxWidth="sm"
            aria-labelledby={`${inputId}-title`}
            TransitionProps={{
                onEntered: () => inputRef.current?.focus(),
            }}
        >
            <DialogTitle id={`${inputId}-title`} sx={{ pb: 0 }}>
                Command palette
            </DialogTitle>
            <Typography variant="caption" color="text.secondary" sx={{ px: 3, pb: 1, display: "block" }}>
                {shortcut} to open. Arrow keys move, Enter opens, Esc closes.
            </Typography>
            <DialogContent sx={{ pt: 0 }}>
                <TextField
                    inputRef={inputRef}
                    id={inputId}
                    autoFocus
                    fullWidth
                    size="small"
                    placeholder="Search pages, projects, runs…"
                    value={q}
                    onChange={(e) => {
                        setQ(e.target.value);
                        setActiveIndex(0);
                    }}
                    onKeyDown={handleListKeyDown}
                    inputProps={{
                        role: "combobox",
                        "aria-expanded": true,
                        "aria-controls": listboxId,
                        "aria-autocomplete": "list",
                        "aria-activedescendant": activeDescendantId,
                    }}
                    sx={{ mb: 1 }}
                />
                <List
                    dense
                    disablePadding
                    id={listboxId}
                    role="listbox"
                    aria-label="Commands"
                    sx={{ maxHeight: 420, overflow: "auto", outline: "none" }}
                >
                    {grouped.map((section) => (
                        <Box key={section.group} component="li" sx={{ listStyle: "none" }}>
                            <Typography
                                variant="overline"
                                color="text.secondary"
                                sx={{ display: "block", px: 1.5, pt: 1.25, pb: 0.5 }}
                            >
                                {GROUP_LABEL[section.group]}
                            </Typography>
                            {section.items.map((item) => {
                                const index = flat.findIndex((entry) => entry.id === item.id);
                                return (
                                    <ListItemButton
                                        key={item.id}
                                        id={`${listboxId}-option-${item.id}`}
                                        role="option"
                                        aria-selected={index === safeActiveIndex}
                                        selected={index === safeActiveIndex}
                                        onMouseEnter={() => setActiveIndex(index)}
                                        onClick={() => selectItem(item)}
                                    >
                                        <ListItemText
                                            primary={item.label}
                                            secondary={item.secondary ?? item.path}
                                        />
                                    </ListItemButton>
                                );
                            })}
                        </Box>
                    ))}
                    {flat.length === 0 && (
                        <Typography variant="body2" color="text.secondary" sx={{ py: 2, px: 1 }}>
                            No matches. Try a page name, project, or run id.
                        </Typography>
                    )}
                </List>
            </DialogContent>
        </Dialog>
    );
}
