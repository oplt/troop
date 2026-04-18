import { useMemo, useState } from "react";
import {
    Accordion,
    AccordionDetails,
    AccordionSummary,
    Alert,
    Box,
    Button,
    Chip,
    Drawer,
    MenuItem,
    Paper,
    Stack,
    TextField,
    Typography,
} from "@mui/material";
import {
    CheckCircleOutline as AcceptIcon,
    Code as CodeIcon,
    ExpandMore as ExpandMoreIcon,
    Link as MapIcon,
    VisibilityOffOutlined as IgnoreIcon,
} from "@mui/icons-material";

import {
    applySkillUnmatchedSectionMapping,
    draftToSkillTemplateFormState,
    getSkillImportConfidenceLabel,
    getSkillUnknownTools,
    mapSkillUnknownTool,
    updateSkillImportDraftField,
} from "./parser";
import type { SkillImportIssue, SkillImportTargetField, SkillTemplateImportDraft } from "./types";

type Props = {
    open: boolean;
    draft: SkillTemplateImportDraft | null;
    toolCatalog: string[];
    onClose: () => void;
    onContinue: (draft: SkillTemplateImportDraft) => void;
};

const TARGET_OPTIONS: Array<{ value: SkillImportTargetField; label: string }> = [
    { value: "description", label: "Append to description" },
    { value: "rules_markdown", label: "Append to rules" },
    { value: "tags", label: "Convert to tags" },
    { value: "ignore", label: "Ignore section" },
];

function severityColor(severity: SkillImportIssue["severity"]): "error" | "warning" | "info" {
    if (severity === "error") return "error";
    if (severity === "warning") return "warning";
    return "info";
}

function confidenceColor(confidence: number): "success" | "warning" | "error" {
    const label = getSkillImportConfidenceLabel(confidence);
    if (label === "high") return "success";
    if (label === "medium") return "warning";
    return "error";
}

function issueFieldLabel(field?: string) {
    return field ? field.replace(/_/g, " ") : "General";
}

export function SkillTemplateImportReviewDrawer({ open, draft, toolCatalog, onClose, onContinue }: Props) {
    const [workingDraft, setWorkingDraft] = useState<SkillTemplateImportDraft | null>(draft);
    const [dismissedIssueIds, setDismissedIssueIds] = useState<string[]>([]);
    const [unmatchedTargets, setUnmatchedTargets] = useState<Record<string, SkillImportTargetField>>({});
    const [toolMappings, setToolMappings] = useState<Record<string, string>>({});

    const visibleIssues = useMemo(
        () => (workingDraft?.issues ?? []).filter((issue) => !dismissedIssueIds.includes(issue.id)),
        [dismissedIssueIds, workingDraft?.issues],
    );
    const blockingIssues = useMemo(
        () => visibleIssues.filter((issue) => issue.severity === "error"),
        [visibleIssues],
    );
    const unknownTools = useMemo(
        () => (workingDraft ? getSkillUnknownTools(workingDraft, toolCatalog) : []),
        [toolCatalog, workingDraft],
    );
    const previewForm = useMemo(
        () => (workingDraft ? draftToSkillTemplateFormState(workingDraft) : null),
        [workingDraft],
    );

    if (!workingDraft) {
        return null;
    }

    function updateField(field: keyof SkillTemplateImportDraft["parsed"], value: string) {
        const listField = field === "capabilities" || field === "allowed_tools" || field === "tags";
        const nextValue = listField ? value.split(",").map((item) => item.trim()).filter(Boolean) : value;
        setWorkingDraft((current) => current ? updateSkillImportDraftField(current, field, nextValue, toolCatalog) : current);
    }

    return (
        <Drawer anchor="right" open={open} onClose={onClose} PaperProps={{ sx: { width: { xs: "100vw", lg: 720 } } }}>
            <Stack spacing={2} sx={{ p: 3 }}>
                <Stack direction={{ xs: "column", sm: "row" }} justifyContent="space-between" spacing={1.5}>
                    <Box>
                        <Typography variant="h6">Review skill Markdown import</Typography>
                        <Typography variant="body2" color="text.secondary">
                            Resolve parser ambiguity here first. Final polish still happens in the normal skill drawer.
                        </Typography>
                    </Box>
                    <Stack direction="row" spacing={1}>
                        <Button onClick={onClose}>Close</Button>
                        <Button variant="contained" disabled={blockingIssues.length > 0} onClick={() => onContinue(workingDraft)}>
                            Continue to drawer
                        </Button>
                    </Stack>
                </Stack>

                <Alert severity={blockingIssues.length > 0 ? "error" : visibleIssues.some((issue) => issue.severity === "warning") ? "warning" : "success"}>
                    Imported from Markdown
                    {workingDraft.source_filename ? `: ${workingDraft.source_filename}` : ""}{" "}
                    • {visibleIssues.length} issue{visibleIssues.length === 1 ? "" : "s"} • {workingDraft.unmatched_sections.length} unmatched
                </Alert>

                <Paper variant="outlined" sx={{ p: 2, borderRadius: 3 }}>
                    <Stack direction={{ xs: "column", md: "row" }} spacing={1.5} justifyContent="space-between">
                        <Box>
                            <Typography variant="overline" color="text.secondary">Import confidence</Typography>
                            <Typography variant="subtitle1">{previewForm?.name || "Untitled skill import"}</Typography>
                            <Typography variant="body2" color="text.secondary">
                                Inline edits update the normalized draft before it reaches the skill builder.
                            </Typography>
                        </Box>
                        <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                            <Chip color={confidenceColor(workingDraft.confidence)} label={`Confidence ${getSkillImportConfidenceLabel(workingDraft.confidence)}`} variant="outlined" />
                            <Chip size="small" variant="outlined" label={`${visibleIssues.filter((issue) => issue.severity === "warning").length} warnings`} />
                            <Chip size="small" variant="outlined" label={`${blockingIssues.length} blocking`} />
                        </Stack>
                    </Stack>
                </Paper>

                <Paper variant="outlined" sx={{ p: 2, borderRadius: 3 }}>
                    <Stack spacing={2}>
                        <Typography variant="subtitle2">Parsed values</Typography>
                        <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
                            <TextField label="Name" value={workingDraft.parsed.name ?? ""} onChange={(event) => updateField("name", event.target.value)} fullWidth />
                            <TextField label="Slug" value={workingDraft.parsed.slug ?? ""} onChange={(event) => updateField("slug", event.target.value)} fullWidth />
                        </Stack>
                        <TextField label="Description" value={workingDraft.parsed.description ?? ""} onChange={(event) => updateField("description", event.target.value)} multiline minRows={3} />
                        <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
                            <TextField label="Capabilities" value={workingDraft.parsed.capabilities.join(", ")} onChange={(event) => updateField("capabilities", event.target.value)} fullWidth />
                            <TextField label="Allowed tools" value={workingDraft.parsed.allowed_tools.join(", ")} onChange={(event) => updateField("allowed_tools", event.target.value)} fullWidth />
                        </Stack>
                        <TextField label="Tags" value={workingDraft.parsed.tags.join(", ")} onChange={(event) => updateField("tags", event.target.value)} fullWidth />
                        <TextField label="Rules" value={workingDraft.parsed.rules_markdown ?? ""} onChange={(event) => updateField("rules_markdown", event.target.value)} multiline minRows={6} />
                    </Stack>
                </Paper>

                {unknownTools.length > 0 ? (
                    <Paper variant="outlined" sx={{ p: 2, borderRadius: 3 }}>
                        <Stack spacing={1.5}>
                            <Typography variant="subtitle2">Unknown tools</Typography>
                            {unknownTools.map((tool) => (
                                <Stack key={tool} direction={{ xs: "column", md: "row" }} spacing={1.5}>
                                    <TextField label="Imported tool" value={tool} InputProps={{ readOnly: true }} fullWidth />
                                    <TextField select label="Map to known tool" value={toolMappings[tool] ?? ""} onChange={(event) => setToolMappings((current) => ({ ...current, [tool]: event.target.value }))} fullWidth>
                                        <MenuItem value="">Choose tool</MenuItem>
                                        {toolCatalog.map((candidate) => (
                                            <MenuItem key={candidate} value={candidate}>{candidate}</MenuItem>
                                        ))}
                                    </TextField>
                                    <Stack direction="row" spacing={1}>
                                        <Button variant="outlined" startIcon={<MapIcon />} disabled={!toolMappings[tool]} onClick={() => setWorkingDraft((current) => current ? mapSkillUnknownTool(current, tool, toolMappings[tool], toolCatalog) : current)}>
                                            Map
                                        </Button>
                                        <Button variant="text" startIcon={<AcceptIcon />} onClick={() => setDismissedIssueIds((current) => current.concat(`unknown-tool-${tool.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`))}>
                                            Accept
                                        </Button>
                                    </Stack>
                                </Stack>
                            ))}
                        </Stack>
                    </Paper>
                ) : null}

                {workingDraft.unmatched_sections.length > 0 ? (
                    <Paper variant="outlined" sx={{ p: 2, borderRadius: 3 }}>
                        <Stack spacing={1.5}>
                            <Typography variant="subtitle2">Unmatched sections</Typography>
                            {workingDraft.unmatched_sections.map((section) => (
                                <Paper key={section.id} variant="outlined" sx={{ p: 1.5, borderRadius: 2 }}>
                                    <Stack spacing={1}>
                                        <Typography variant="subtitle2">{section.heading || "Untitled section"}</Typography>
                                        <Typography variant="caption" color="text.secondary">{section.reason}</Typography>
                                        <Typography variant="body2" sx={{ whiteSpace: "pre-wrap" }}>{section.content}</Typography>
                                        <Stack direction={{ xs: "column", md: "row" }} spacing={1}>
                                            <TextField
                                                select
                                                label="Map section"
                                                value={unmatchedTargets[section.id] ?? "rules_markdown"}
                                                onChange={(event) => setUnmatchedTargets((current) => ({ ...current, [section.id]: event.target.value as SkillImportTargetField }))}
                                                fullWidth
                                            >
                                                {TARGET_OPTIONS.map((option) => (
                                                    <MenuItem key={option.value} value={option.value}>{option.label}</MenuItem>
                                                ))}
                                            </TextField>
                                            <Stack direction="row" spacing={1}>
                                                <Button variant="outlined" startIcon={<MapIcon />} onClick={() => setWorkingDraft((current) => current ? applySkillUnmatchedSectionMapping(current, section.id, unmatchedTargets[section.id] ?? "rules_markdown", toolCatalog) : current)}>
                                                    Map
                                                </Button>
                                                <Button variant="text" startIcon={<IgnoreIcon />} onClick={() => setWorkingDraft((current) => current ? applySkillUnmatchedSectionMapping(current, section.id, "ignore", toolCatalog) : current)}>
                                                    Ignore
                                                </Button>
                                            </Stack>
                                        </Stack>
                                    </Stack>
                                </Paper>
                            ))}
                        </Stack>
                    </Paper>
                ) : null}

                <Paper variant="outlined" sx={{ p: 2, borderRadius: 3 }}>
                    <Stack spacing={1.5}>
                        <Typography variant="subtitle2">Issues</Typography>
                        {visibleIssues.length === 0 ? (
                            <Alert severity="success">No blocking import issues remain.</Alert>
                        ) : (
                            visibleIssues.map((issue) => (
                                <Paper key={issue.id} variant="outlined" sx={{ p: 1.5, borderRadius: 2 }}>
                                    <Stack spacing={1}>
                                        <Stack direction={{ xs: "column", md: "row" }} spacing={1} justifyContent="space-between">
                                            <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                                                <Chip size="small" color={severityColor(issue.severity)} label={issue.severity} />
                                                <Chip size="small" variant="outlined" label={issueFieldLabel(issue.field)} />
                                            </Stack>
                                            {issue.severity !== "error" ? (
                                                <Button size="small" startIcon={<AcceptIcon />} onClick={() => setDismissedIssueIds((current) => current.concat(issue.id))}>
                                                    Accept
                                                </Button>
                                            ) : null}
                                        </Stack>
                                        <Typography variant="body2">{issue.message}</Typography>
                                        {issue.sourceExcerpt ? (
                                            <Typography variant="caption" color="text.secondary" sx={{ whiteSpace: "pre-wrap" }}>
                                                Source: {issue.sourceExcerpt}
                                            </Typography>
                                        ) : null}
                                    </Stack>
                                </Paper>
                            ))
                        )}
                    </Stack>
                </Paper>

                <Accordion>
                    <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                        <Stack direction="row" spacing={1} alignItems="center">
                            <CodeIcon fontSize="small" />
                            <Typography variant="subtitle2">Advanced JSON</Typography>
                        </Stack>
                    </AccordionSummary>
                    <AccordionDetails>
                        <Box component="pre" sx={{ m: 0, p: 2, borderRadius: 2, bgcolor: "grey.950", color: "grey.100", overflow: "auto", fontSize: 12 }}>
                            {JSON.stringify(workingDraft, null, 2)}
                        </Box>
                    </AccordionDetails>
                </Accordion>
            </Stack>
        </Drawer>
    );
}
