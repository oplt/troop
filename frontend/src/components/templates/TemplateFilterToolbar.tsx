import { useMemo, useState } from "react";
import {
    Box,
    Button,
    Chip,
    Menu,
    Paper,
    Stack,
    Typography,
} from "@mui/material";
import {
    Clear as ClearIcon,
    Close as CloseIcon,
    KeyboardArrowDown as ArrowIcon,
} from "@mui/icons-material";

import type { TemplateFilterState } from "./types";

export type FilterOptionGroup = {
    key: keyof TemplateFilterState;
    label: string;
    options: string[];
    single?: boolean;
};

type TemplateFilterToolbarProps = {
    value: TemplateFilterState;
    groups: readonly FilterOptionGroup[];
    onChange: (next: TemplateFilterState) => void;
};

export function TemplateFilterToolbar({ value, groups, onChange }: TemplateFilterToolbarProps) {
    const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null);
    const [openGroup, setOpenGroup] = useState<FilterOptionGroup | null>(null);

    const activeChips = useMemo(() => {
        const chips: Array<{ key: string; label: string; onDelete: () => void }> = [];
        if (value.type !== "all") {
            chips.push({ key: `type-${value.type}`, label: value.type, onDelete: () => onChange({ ...value, type: "all" }) });
        }
        value.roles.forEach((item) => chips.push({ key: `roles-${item}`, label: item, onDelete: () => onChange({ ...value, roles: value.roles.filter((v) => v !== item) }) }));
        value.domains.forEach((item) => chips.push({ key: `domains-${item}`, label: item, onDelete: () => onChange({ ...value, domains: value.domains.filter((v) => v !== item) }) }));
        value.outcomes.forEach((item) => chips.push({ key: `outcomes-${item}`, label: item, onDelete: () => onChange({ ...value, outcomes: value.outcomes.filter((v) => v !== item) }) }));
        value.tools.forEach((item) => chips.push({ key: `tools-${item}`, label: item, onDelete: () => onChange({ ...value, tools: value.tools.filter((v) => v !== item) }) }));
        value.autonomy.forEach((item) => chips.push({ key: `autonomy-${item}`, label: item, onDelete: () => onChange({ ...value, autonomy: value.autonomy.filter((v) => v !== item) }) }));
        value.visibility.forEach((item) => chips.push({ key: `visibility-${item}`, label: item, onDelete: () => onChange({ ...value, visibility: value.visibility.filter((v) => v !== item) }) }));
        return chips;
    }, [onChange, value]);

    function isActive(group: FilterOptionGroup) {
        const current = value[group.key];
        if (group.key === "type") return current !== "all";
        if (group.key === "sortBy") return Boolean(current);
        return Array.isArray(current) ? current.length > 0 : Boolean(current);
    }

    function toggleOption(group: FilterOptionGroup, option: string) {
        if (group.key === "type") {
            onChange({ ...value, type: value.type === option ? "all" : (option as TemplateFilterState["type"]) });
            return;
        }
        if (group.key === "sortBy") {
            onChange({ ...value, sortBy: value.sortBy === option ? "" : option });
            return;
        }
        const current = value[group.key];
        if (!Array.isArray(current)) return;
        const next = group.single
            ? current.includes(option)
                ? []
                : [option]
            : current.includes(option)
              ? current.filter((item) => item !== option)
              : [...current, option];
        onChange({ ...value, [group.key]: next });
    }

    function clearAll() {
        onChange({
            type: "all",
            roles: [],
            domains: [],
            outcomes: [],
            tools: [],
            autonomy: [],
            visibility: [],
            sortBy: "",
        });
    }

    return (
        <Paper sx={{ p: 2.25, borderRadius: 4 }}>
            <Stack spacing={2}>
                <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1.25 }}>
                    {groups.map((group) => (
                        <Button
                            key={group.key}
                            variant="outlined"
                            endIcon={<ArrowIcon />}
                            onClick={(event) => {
                                setAnchorEl(event.currentTarget);
                                setOpenGroup(group);
                            }}
                            sx={{
                                minHeight: 44,
                                px: 2,
                                borderRadius: 999,
                                textTransform: "none",
                                color: "text.primary",
                                borderColor: isActive(group) ? "info.main" : "divider",
                                bgcolor: isActive(group) ? "#e8fbff" : "background.paper",
                                "&:hover": {
                                    borderColor: isActive(group) ? "info.main" : "text.disabled",
                                    bgcolor: isActive(group) ? "#e8fbff" : "#fbfcfd",
                                },
                            }}
                        >
                            {group.label}
                        </Button>
                    ))}
                </Box>

                <Stack
                    direction={{ xs: "column", md: "row" }}
                    justifyContent="space-between"
                    alignItems={{ xs: "flex-start", md: "center" }}
                    spacing={1.25}
                >
                    <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1 }}>
                        {activeChips.map((chip) => (
                            <Chip
                                key={chip.key}
                                label={chip.label}
                                onDelete={chip.onDelete}
                                deleteIcon={<CloseIcon />}
                                sx={{
                                    height: 42,
                                    borderRadius: 999,
                                    bgcolor: "#f2f6f5",
                                    border: "1px solid",
                                    borderColor: "divider",
                                    "& .MuiChip-deleteIcon": {
                                        color: "text.secondary",
                                    },
                                }}
                            />
                        ))}
                    </Box>
                    <Button
                        variant="text"
                        startIcon={<ClearIcon />}
                        onClick={clearAll}
                        sx={{
                            color: "info.main",
                            textTransform: "none",
                            alignSelf: { xs: "flex-end", md: "center" },
                        }}
                    >
                        Clear filters
                    </Button>
                </Stack>
            </Stack>

            <Menu
                anchorEl={anchorEl}
                open={Boolean(anchorEl && openGroup)}
                onClose={() => {
                    setAnchorEl(null);
                    setOpenGroup(null);
                }}
                PaperProps={{
                    sx: {
                        mt: 1,
                        p: 1.5,
                        minWidth: 240,
                        borderRadius: 3,
                    },
                }}
            >
                <Stack spacing={0.5}>
                    <Typography variant="subtitle2" sx={{ px: 0.5, pb: 0.5 }}>
                        {openGroup?.label}
                    </Typography>
                    {openGroup?.options.map((option) => {
                        const selected = openGroup.key === "type"
                            ? value.type === option
                            : openGroup.key === "sortBy"
                              ? value.sortBy === option
                              : Array.isArray(value[openGroup.key]) && value[openGroup.key].includes(option);
                        return (
                            <Button
                                key={`${openGroup.key}-${option}`}
                                variant={selected ? "contained" : "text"}
                                onClick={() => toggleOption(openGroup, option)}
                                sx={{
                                    justifyContent: "flex-start",
                                    borderRadius: 2,
                                    textTransform: "none",
                                }}
                            >
                                {option}
                            </Button>
                        );
                    })}
                </Stack>
            </Menu>
        </Paper>
    );
}
