import { Button, MenuItem, Paper, Stack, TextField, Typography } from "@mui/material";

export type ExternalLinkRecord = {
    id: string;
    kind: string;
    label: string;
    url: string;
    notes: string;
};

const LINK_KINDS = [
    ["spec", "Spec"], ["doc", "Doc"], ["figma", "Figma"], ["pr", "PR"],
    ["commit", "Commit"], ["incident", "Incident"], ["runbook", "Runbook"],
    ["issue", "Issue"], ["other", "Other"],
] as const;

function createLinkId() {
    return `link-${Math.random().toString(36).slice(2, 10)}`;
}

export function ExternalLinksEditor({
    links,
    onChange,
    compact = false,
}: {
    links: ExternalLinkRecord[];
    onChange: (links: ExternalLinkRecord[]) => void;
    compact?: boolean;
}) {
    const update = (index: number, patch: Partial<ExternalLinkRecord>) => {
        onChange(links.map((item, itemIndex) => itemIndex === index ? { ...item, ...patch } : item));
    };

    return (
        <Stack spacing={1}>
            {links.length === 0 && <Typography variant="caption" color="text.secondary">No external links yet.</Typography>}
            {links.map((link, index) => (
                <Paper key={link.id} variant="outlined" sx={{ p: compact ? 1 : 1.25, borderRadius: 1 }}>
                    <Stack spacing={1}>
                        <Stack direction={{ xs: "column", md: "row" }} spacing={1}>
                            <TextField select size="small" label="Type" value={link.kind} onChange={(event) => update(index, { kind: event.target.value })} sx={{ minWidth: 120 }}>
                                {LINK_KINDS.map(([value, label]) => <MenuItem key={value} value={value}>{label}</MenuItem>)}
                            </TextField>
                            <TextField size="small" label="Label" value={link.label} onChange={(event) => update(index, { label: event.target.value })} fullWidth />
                            <Button size="small" color="error" onClick={() => onChange(links.filter((item) => item.id !== link.id))}>Remove</Button>
                        </Stack>
                        <TextField size="small" label="URL" value={link.url} onChange={(event) => update(index, { url: event.target.value })} fullWidth />
                        <TextField size="small" label="Notes" value={link.notes} onChange={(event) => update(index, { notes: event.target.value })} multiline minRows={compact ? 2 : 1} fullWidth />
                    </Stack>
                </Paper>
            ))}
            <Button size="small" variant="outlined" onClick={() => onChange([...links, { id: createLinkId(), kind: "doc", label: "", url: "", notes: "" }])}>Add link</Button>
        </Stack>
    );
}
