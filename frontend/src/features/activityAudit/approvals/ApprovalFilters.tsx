import { MenuItem, Paper, Stack, TextField, Typography } from "@mui/material";

import type { Agent, OrchestrationProject } from "../../../api/orchestration";
import { FilterToolbar } from "../../../components/ui/FilterToolbar";

type ApprovalFiltersProps = {
    dateFrom: string;
    dateTo: string;
    projectFilter: string;
    agentFilter: string;
    projects: OrchestrationProject[];
    agents: Agent[];
    onDateFromChange: (value: string) => void;
    onDateToChange: (value: string) => void;
    onProjectFilterChange: (value: string) => void;
    onAgentFilterChange: (value: string) => void;
};

export function ApprovalFilters({
    dateFrom,
    dateTo,
    projectFilter,
    agentFilter,
    projects,
    agents,
    onDateFromChange,
    onDateToChange,
    onProjectFilterChange,
    onAgentFilterChange,
}: ApprovalFiltersProps) {
    return (
        <Paper sx={{ p: 2, borderRadius: 1 }}>
            <Stack spacing={2}>
                <Typography variant="body2" color="text.secondary">
                    Decide pending cards first. Ledger and Audit are history.
                </Typography>
                <FilterToolbar>
                    <TextField
                        label="From date"
                        type="date"
                        size="small"
                        value={dateFrom}
                        onChange={(e) => onDateFromChange(e.target.value)}
                        InputLabelProps={{ shrink: true }}
                        sx={{ minWidth: 160 }}
                    />
                    <TextField
                        label="To date"
                        type="date"
                        size="small"
                        value={dateTo}
                        onChange={(e) => onDateToChange(e.target.value)}
                        InputLabelProps={{ shrink: true }}
                        sx={{ minWidth: 160 }}
                    />
                    <TextField
                        select
                        label="Project"
                        size="small"
                        value={projectFilter}
                        onChange={(e) => onProjectFilterChange(e.target.value)}
                        sx={{ minWidth: 200 }}
                    >
                        <MenuItem value="">All projects</MenuItem>
                        {projects.map((p) => (
                            <MenuItem key={p.id} value={p.id}>
                                {p.name}
                            </MenuItem>
                        ))}
                    </TextField>
                    <TextField
                        select
                        label="Agent"
                        size="small"
                        value={agentFilter}
                        onChange={(e) => onAgentFilterChange(e.target.value)}
                        sx={{ minWidth: 200 }}
                    >
                        <MenuItem value="">Any agent</MenuItem>
                        {agents.map((a) => (
                            <MenuItem key={a.id} value={a.id}>
                                {a.name}
                            </MenuItem>
                        ))}
                    </TextField>
                </FilterToolbar>
            </Stack>
        </Paper>
    );
}
