import { Paper, Stack, TextField, Typography } from "@mui/material";

type TemplateTopBarProps = {
    searchQuery: string;
    onSearchQueryChange: (value: string) => void;
};

export function TemplateTopBar({
    searchQuery,
    onSearchQueryChange,
}: TemplateTopBarProps) {
    return (
        <Paper sx={{ p: 2, borderRadius: 4 }}>
            <Stack spacing={2}>
                <Stack direction={{ xs: "column", lg: "row" }} spacing={2} justifyContent="space-between">
                    <div>
                        <Typography variant="h5">Template workspace</Typography>
                        <Typography variant="body2" color="text.secondary">
                            Browse patterns, build agent configs, manage template registry.
                        </Typography>
                    </div>
                    <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5}>
                        <TextField
                            size="small"
                            label="Search templates"
                            value={searchQuery}
                            onChange={(event) => onSearchQueryChange(event.target.value)}
                            sx={{ minWidth: { sm: 260 } }}
                        />
                    </Stack>
                </Stack>
            </Stack>
        </Paper>
    );
}
