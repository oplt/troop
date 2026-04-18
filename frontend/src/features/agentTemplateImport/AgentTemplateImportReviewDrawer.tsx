import { useMemo, useState } from "react";
import {
    Alert,
    Accordion,
    AccordionDetails,
    AccordionSummary,
    Box,
    Button,
    Chip,
    Divider,
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
    applyUnmatchedSectionMapping,
    draftToAgentTemplateFormState,
    getImportConfidenceLabel,
    getUnknownTools,
    mapUnknownTool,
    updateImportDraftParsedField,
} from "./parser";
import type { AgentTemplateImportDraft, ImportIssue, ImportTargetField } from "./types";

type AgentTemplateImportReviewDrawerProps = {
    open: boolean;
    draft: AgentTemplateImportDraft | null;
    toolCatalog: string[];
    onClose: () => void;
    onContinue: (draft: AgentTemplateImportDraft) => void;
};

type DraftFieldKey = keyof AgentTemplateImportDraft["parsed"];

const APPEND_TARGET_OPTIONS: Array<{ value: ImportTargetField; label: string }> = [
    { value: "mission_markdown", label: "Append to mission" },
    { value: "system_prompt", label: "Append to system prompt" },
    { value: "rules_markdown", label: "Append to rules" },
    { value: "output_contract_markdown", label: "Append to output contract" },
    { value: "ignore", label: "Ignore section" },
];

function severityColor(severity: ImportIssue["severity"]): "error" | "warning" | "info" {
    if (severity === "error") return "error";
    if (severity === "warning") return "warning";
    return "info";
}

function confidenceColor(confidence: number): "success" | "warning" | "error" {
    const label = getImportConfidenceLabel(confidence);
    if (label === "high") return "success";
    if (label === "medium") return "warning";
    return "error";
}

function csvValue(value: string[]) {
    return value.join(", ");
}

function inlineListValue(value: string[]) {
    return value.join("\n");
}

function issueFieldLabel(field?: string) {
    if (!field) return "General";
    return field.replace(/_/g, " ");
}

export function AgentTemplateImportReviewDrawer({
    open,
    draft,
    toolCatalog,
    onClose,
    onContinue,
}: AgentTemplateImportReviewDrawerProps) {
    const [workingDraft, setWorkingDraft] = useState<AgentTemplateImportDraft | null>(draft);
    const [dismissedIssueIds, setDismissedIssueIds] = useState<string[]>([]);
    const [unmatchedTargets, setUnmatchedTargets] = useState<Record<string, ImportTargetField>>({});
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
        () => (workingDraft ? getUnknownTools(workingDraft, toolCatalog) : []),
        [toolCatalog, workingDraft],
    );
    const previewForm = useMemo(
        () => (workingDraft ? draftToAgentTemplateFormState(workingDraft) : null),
        [workingDraft],
    );

    if (!workingDraft) {
        return null;
    }

    function updateField(field: DraftFieldKey, value: string) {
        const isListField = field === "allowed_tools" || field === "capabilities" || field === "tags";
        const isMultilineListField = field === "task_filters";
        const nextValue = isListField
            ? value.split(",").map((item) => item.trim()).filter(Boolean)
            : isMultilineListField
                ? value.split("\n").map((item) => item.trim()).filter(Boolean)
                : value;
        setWorkingDraft((current) => current ? updateImportDraftParsedField(current, field, nextValue, toolCatalog) : current);
    }

    function applySection(sectionId: string, target: ImportTargetField) {
        setWorkingDraft((current) => current ? applyUnmatchedSectionMapping(current, sectionId, target, toolCatalog) : current);
    }

    function resolveTool(sourceTool: string) {
        const resolvedTool = toolMappings[sourceTool];
        if (!resolvedTool) {
            return;
        }
        setWorkingDraft((current) => current ? mapUnknownTool(current, { sourceTool, resolvedTool }, toolCatalog) : current);
    }

    return (
        <Drawer
            anchor="right"
            open={open}
            onClose={onClose}
            PaperProps={{ sx: { width: { xs: "100vw", lg: 760 } } }}
        >
            <Stack spacing={2} sx={{ p: 3 }}>
                <Stack direction={{ xs: "column", sm: "row" }} justifyContent="space-between" spacing={1.5}>
                    <Box>
                        <Typography variant="h6">Review Markdown import</Typography>
                        <Typography variant="body2" color="text.secondary">
                            Resolve parser ambiguity here first. Final polish stays in the normal agent template drawer.
                        </Typography>
                    </Box>
                    <Stack direction="row" spacing={1}>
                        <Button onClick={onClose}>Close</Button>
                        <Button
                            variant="contained"
                            onClick={() => onContinue(workingDraft)}
                            disabled={blockingIssues.length > 0}
                        >
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
                            <Typography variant="subtitle1">
                                {previewForm?.name || "Untitled import"}
                            </Typography>
                            <Typography variant="body2" color="text.secondary">
                                Inline edits update the normalized draft before it reaches the final form drawer.
                            </Typography>
                        </Box>
                        <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" sx={{ alignItems: "flex-start" }}>
                            <Chip
                                color={confidenceColor(workingDraft.confidence)}
                                label={`Confidence ${getImportConfidenceLabel(workingDraft.confidence)}`}
                                variant="outlined"
                            />
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
                        <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
                            <TextField select label="Role" value={workingDraft.parsed.role ?? "specialist"} onChange={(event) => updateField("role", event.target.value)} fullWidth>
                                <MenuItem value="manager">manager</MenuItem>
                                <MenuItem value="specialist">specialist</MenuItem>
                                <MenuItem value="reviewer">reviewer</MenuItem>
                            </TextField>
                            <TextField label="Parent template slug" value={workingDraft.parsed.parent_template_slug ?? ""} onChange={(event) => updateField("parent_template_slug", event.target.value)} fullWidth />
                        </Stack>
                        <TextField label="Description" value={workingDraft.parsed.description ?? ""} onChange={(event) => updateField("description", event.target.value)} multiline minRows={2} />
                        <TextField label="Mission" value={workingDraft.parsed.mission_markdown ?? ""} onChange={(event) => updateField("mission_markdown", event.target.value)} multiline minRows={3} />
                        <TextField label="System prompt" value={workingDraft.parsed.system_prompt ?? ""} onChange={(event) => updateField("system_prompt", event.target.value)} multiline minRows={4} />
                        <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
                            <TextField label="Allowed tools" value={csvValue(workingDraft.parsed.allowed_tools)} onChange={(event) => updateField("allowed_tools", event.target.value)} fullWidth helperText="Comma separated tool names." />
                            <TextField label="Capabilities" value={csvValue(workingDraft.parsed.capabilities)} onChange={(event) => updateField("capabilities", event.target.value)} fullWidth helperText="Comma separated capabilities." />
                        </Stack>
                        <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
                            <TextField label="Tags" value={csvValue(workingDraft.parsed.tags)} onChange={(event) => updateField("tags", event.target.value)} fullWidth />
                            <TextField label="Task filters" value={inlineListValue(workingDraft.parsed.task_filters)} onChange={(event) => updateField("task_filters", event.target.value)} fullWidth multiline minRows={3} helperText="One routing rule per line." />
                        </Stack>
                        <TextField label="Rules" value={workingDraft.parsed.rules_markdown ?? ""} onChange={(event) => updateField("rules_markdown", event.target.value)} multiline minRows={3} />
                        <TextField label="Output contract" value={workingDraft.parsed.output_contract_markdown ?? ""} onChange={(event) => updateField("output_contract_markdown", event.target.value)} multiline minRows={3} />
                    </Stack>
                </Paper>

                {unknownTools.length > 0 ? (
                    <Paper variant="outlined" sx={{ p: 2, borderRadius: 3 }}>
                        <Stack spacing={1.5}>
                            <Typography variant="subtitle2">Unknown tools</Typography>
                            {unknownTools.map((tool) => (
                                <Stack key={tool} direction={{ xs: "column", md: "row" }} spacing={1.5}>
                                    <TextField label="Imported tool" value={tool} InputProps={{ readOnly: true }} fullWidth />
                                    <TextField
                                        select
                                        label="Map to known tool"
                                        value={toolMappings[tool] ?? ""}
                                        onChange={(event) => setToolMappings((current) => ({ ...current, [tool]: event.target.value }))}
                                        fullWidth
                                    >
                                        <MenuItem value="">Choose tool</MenuItem>
                                        {toolCatalog.map((candidate) => (
                                            <MenuItem key={candidate} value={candidate}>{candidate}</MenuItem>
                                        ))}
                                    </TextField>
                                    <Stack direction="row" spacing={1}>
                                        <Button variant="outlined" startIcon={<MapIcon />} onClick={() => resolveTool(tool)} disabled={!toolMappings[tool]}>
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
                                                value={unmatchedTargets[section.id] ?? "mission_markdown"}
                                                onChange={(event) => setUnmatchedTargets((current) => ({ ...current, [section.id]: event.target.value as ImportTargetField }))}
                                                fullWidth
                                            >
                                                {APPEND_TARGET_OPTIONS.map((option) => (
                                                    <MenuItem key={option.value} value={option.value}>{option.label}</MenuItem>
                                                ))}
                                            </TextField>
                                            <Stack direction="row" spacing={1}>
                                                <Button variant="outlined" startIcon={<MapIcon />} onClick={() => applySection(section.id, unmatchedTargets[section.id] ?? "mission_markdown")}>
                                                    Map
                                                </Button>
                                                <Button variant="text" startIcon={<IgnoreIcon />} onClick={() => applySection(section.id, "ignore")}>
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
                                <Paper
                                    key={issue.id}
                                    variant="outlined"
                                    sx={{
                                        p: 1.5,
                                        borderRadius: 2,
                                        borderColor: `${severityColor(issue.severity)}.main`,
                                        bgcolor: (theme) => theme.palette[severityColor(issue.severity)].lighter ?? theme.palette.action.hover,
                                    }}
                                >
                                    <Stack spacing={1}>
                                        <Stack direction={{ xs: "column", md: "row" }} spacing={1} justifyContent="space-between">
                                            <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                                                <Chip size="small" color={severityColor(issue.severity)} label={issue.severity} />
                                                <Chip size="small" variant="outlined" label={issueFieldLabel(issue.field)} />
                                                {issue.sourceHeading ? <Chip size="small" variant="outlined" label={issue.sourceHeading} /> : null}
                                            </Stack>
                                            {issue.severity !== "error" ? (
                                                <Button size="small" startIcon={<AcceptIcon />} onClick={() => setDismissedIssueIds((current) => current.concat(issue.id))}>
                                                    Accept
                                                </Button>
                                            ) : (
                                                <Chip size="small" color="error" variant="outlined" label="Edit to resolve" />
                                            )}
                                        </Stack>
                                        <Typography variant="body2">{issue.message}</Typography>
                                        {issue.sourceExcerpt ? (
                                            <Typography variant="caption" color="text.secondary" sx={{ whiteSpace: "pre-wrap" }}>
                                                Source: {issue.sourceExcerpt}
                                            </Typography>
                                        ) : null}
                                        {issue.candidateTargets?.length ? (
                                            <Typography variant="caption" color="text.secondary">
                                                Targets: {issue.candidateTargets.join(", ")}
                                            </Typography>
                                        ) : null}
                                    </Stack>
                                </Paper>
                            ))
                        )}
                    </Stack>
                </Paper>

                <Paper variant="outlined" sx={{ p: 2, borderRadius: 3 }}>
                    <Stack spacing={1.5}>
                        <Typography variant="subtitle2">Drawer preview</Typography>
                        <Typography variant="body2" color="text.secondary">
                            This is what will land in the normal agent template drawer for final edits.
                        </Typography>
                        <Divider />
                        <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
                            <TextField label="Name" value={previewForm?.name ?? ""} InputProps={{ readOnly: true }} fullWidth />
                            <TextField label="Slug" value={previewForm?.slug ?? ""} InputProps={{ readOnly: true }} fullWidth />
                        </Stack>
                        <TextField label="Mission" value={previewForm?.mission_markdown ?? ""} InputProps={{ readOnly: true }} fullWidth multiline minRows={2} />
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
                        <Stack spacing={1.5}>
                            <Alert severity="info">Inspect normalized draft here. Raw JSON is not the main correction path.</Alert>
                            <Box
                                component="pre"
                                sx={{
                                    m: 0,
                                    p: 2,
                                    borderRadius: 2,
                                    bgcolor: "action.hover", // or "grey.100" for light mode / "grey.900" for dark
                                    color: "text.primary",
                                    overflow: "auto",
                                    fontSize: 12,
                                }}
                            >
                                {JSON.stringify(workingDraft, null, 2)}
                            </Box>
                        </Stack>
                    </AccordionDetails>
                </Accordion>
            </Stack>
        </Drawer>
    );
}
