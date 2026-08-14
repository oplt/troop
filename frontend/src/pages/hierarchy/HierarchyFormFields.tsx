import {
    Accordion, AccordionDetails, AccordionSummary, Autocomplete, Box, Chip, Stack, TextField, Typography,
} from "@mui/material";
import { ExpandMore as ExpandMoreIcon } from "@mui/icons-material";
import { SectionCard } from "../../components/ui/SectionCard";
import { parseLooseList } from "./hierarchyGraphUtils";

type StringListFieldProps = {
    label: string;
    value: string[];
    onChange: (nextValue: string[]) => void;
    helperText?: string;
    placeholder?: string;
    options?: string[];
};

export function StringListField({
    label,
    value,
    onChange,
    helperText,
    placeholder,
    options = [],
}: StringListFieldProps) {
    return (
        <Autocomplete
            multiple
            freeSolo
            options={options}
            value={value}
            onChange={(_, nextValue: string[]) => onChange(Array.from(new Set(nextValue.map((item) => item.trim()).filter(Boolean))))}
            renderTags={(tagValue, getTagProps) =>
                tagValue.map((option, index) => {
                    const { key, ...tagProps } = getTagProps({ index });
                    return <Chip key={key} label={option} size="small" {...tagProps} />;
                })
            }
            renderInput={(params) => (
                <TextField
                    {...params}
                    label={label}
                    helperText={helperText}
                    placeholder={placeholder}
                />
            )}
        />
    );
}

export function TaskFiltersField({
    value,
    onChange,
    helperText,
}: {
    value: string[];
    onChange: (nextValue: string[]) => void;
    helperText: string;
}) {
    return (
        <TextField
            label="Task filters"
            value={value.join("\n")}
            onChange={(event) => onChange(parseLooseList(event.target.value))}
            helperText={helperText}
            multiline
            minRows={4}
            fullWidth
        />
    );
}

export function AgentEditorSection({
    step,
    title,
    description,
    children,
    defaultExpanded = true,
}: {
    step?: string;
    title: string;
    description: string;
    children: React.ReactNode;
    defaultExpanded?: boolean;
}) {
    return (
        <Accordion defaultExpanded={defaultExpanded} disableGutters elevation={0} sx={{ border: "1px solid", borderColor: "divider", borderRadius: 1, overflow: "hidden", "&:before": { display: "none" } }}>
            <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                <Stack spacing={0.25}>
                    {step ? (
                        <Typography variant="caption" sx={{ color: "text.secondary", fontWeight: 500 }}>
                            {step}
                        </Typography>
                    ) : null}
                    <Typography variant="subtitle2">{title}</Typography>
                    <Typography variant="body2" color="text.secondary">
                        {description}
                    </Typography>
                </Stack>
            </AccordionSummary>
            <AccordionDetails>
                <Stack spacing={2}>{children}</Stack>
            </AccordionDetails>
        </Accordion>
    );
}

export function ExpandableSection({
    title,
    description,
    children,
    defaultExpanded = true,
    action,
}: {
    title: string;
    description: string;
    children: React.ReactNode;
    defaultExpanded?: boolean;
    action?: React.ReactNode;
}) {
    return (
        <SectionCard sx={{ p: 0, overflow: "hidden" }}>
            <Accordion
                defaultExpanded={defaultExpanded}
                disableGutters
                elevation={0}
                sx={{
                    boxShadow: "none",
                    bgcolor: "transparent",
                    "&:before": { display: "none" },
                }}
            >
                <AccordionSummary expandIcon={<ExpandMoreIcon />} sx={{ px: 2.25, py: 0.5 }}>
                    <Stack direction="row" justifyContent="space-between" alignItems="flex-start" spacing={2} sx={{ width: "100%", pr: 1 }}>
                        <Stack spacing={0.25}>
                            <Typography variant="subtitle2">{title}</Typography>
                            <Typography variant="body2" color="text.secondary">
                                {description}
                            </Typography>
                        </Stack>
                        {action ? (
                            <Box onClick={(event) => event.stopPropagation()}>
                                {action}
                            </Box>
                        ) : null}
                    </Stack>
                </AccordionSummary>
                <AccordionDetails sx={{ px: 2.25, pb: 2.25, pt: 0 }}>
                    <Stack spacing={2}>{children}</Stack>
                </AccordionDetails>
            </Accordion>
        </SectionCard>
    );
}

