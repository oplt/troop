import { useCallback, useMemo, useState, type ReactNode } from "react";
import {
    Alert,
    Box,
    Button,
    Chip,
    Collapse,
    Divider,
    List,
    ListItem,
    ListItemText,
    Paper,
    Stack,
    Typography,
} from "@mui/material";
import { alpha } from "@mui/material/styles";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import { humanizeKey } from "../../utils/formatters";

function isPlainObject(v: unknown): v is Record<string, unknown> {
    return v !== null && typeof v === "object" && !Array.isArray(v);
}

function copyToClipboard(text: string) {
    void navigator.clipboard.writeText(text).catch(() => {});
}

/** Monospace block for power users; optional copy. */
export function CollapsibleRawJson({
    value,
    summary,
    defaultOpen = false,
    maxHeight = 280,
}: {
    value: unknown;
    summary?: string;
    defaultOpen?: boolean;
    maxHeight?: number;
}) {
    const [open, setOpen] = useState(defaultOpen);
    const text = useMemo(() => {
        if (typeof value === "string") return value;
        try {
            return JSON.stringify(value, null, 2);
        } catch {
            return String(value);
        }
    }, [value]);

    return (
        <Box sx={{ mt: summary ? 0.5 : 0 }}>
            {summary && (
                <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
                    {summary}
                </Typography>
            )}
            <Stack direction="row" spacing={1} alignItems="center" sx={{ flexWrap: "wrap", useFlexGap: true }}>
                <Button size="small" variant="text" onClick={() => setOpen((o) => !o)} sx={{ minWidth: 0, px: 0 }}>
                    {open ? "Hide raw JSON" : "View raw JSON"}
                </Button>
                <Button
                    size="small"
                    variant="text"
                    startIcon={<ContentCopyIcon sx={{ fontSize: 16 }} />}
                    onClick={() => copyToClipboard(text)}
                    sx={{ minWidth: 0, px: 0 }}
                >
                    Copy
                </Button>
            </Stack>
            <Collapse in={open}>
                <Box
                    component="pre"
                    role="region"
                    aria-label="Raw JSON"
                    sx={(theme) => ({
                        m: 0,
                        mt: 0.75,
                        p: 1.25,
                        borderRadius: 1.5,
                        maxHeight,
                        overflow: "auto",
                        fontSize: "0.75rem",
                        fontFamily: "IBM Plex Mono, ui-monospace, monospace",
                        whiteSpace: "pre-wrap",
                        wordBreak: "break-word",
                        bgcolor: alpha(theme.palette.text.primary, 0.04),
                        border: `1px solid ${theme.palette.divider}`,
                    })}
                >
                    {text}
                </Box>
            </Collapse>
        </Box>
    );
}

function ScalarLine({ label, value }: { label: string; value: unknown }) {
    if (value === undefined || value === null || value === "") return null;
    const display =
        typeof value === "string" || typeof value === "number" || typeof value === "boolean"
            ? String(value)
            : JSON.stringify(value);
    return (
        <Box>
            <Typography variant="caption" color="text.secondary" component="div">
                {label}
            </Typography>
            <Typography variant="body2" sx={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
                {display.length > 2000 ? `${display.slice(0, 2000)}…` : display}
            </Typography>
        </Box>
    );
}

/** One-level key/value for shallow snapshots. */
export function ShallowKeyValueList({ data, title }: { data: Record<string, unknown>; title?: string }) {
    const entries = Object.entries(data).filter(([, v]) => v !== undefined && v !== null);
    if (entries.length === 0) {
        return <Typography variant="body2" color="text.secondary">No fields.</Typography>;
    }
    return (
        <Stack spacing={1.25}>
            {title && (
                <Typography variant="subtitle2" color="text.secondary">
                    {title}
                </Typography>
            )}
            {entries.map(([key, val]) => (
                <Box key={key}>
                    <Typography variant="caption" color="text.secondary">
                        {humanizeKey(key)}
                    </Typography>
                    {typeof val === "object" && val !== null ? (
                        <Box sx={{ mt: 0.5 }}>
                            <CollapsibleRawJson value={val} defaultOpen={false} maxHeight={220} />
                        </Box>
                    ) : (
                        <Typography variant="body2" sx={{ wordBreak: "break-word" }}>
                            {String(val)}
                        </Typography>
                    )}
                </Box>
            ))}
        </Stack>
    );
}

function TraceStepsList({ trace }: { trace: unknown[] }) {
    return (
        <List dense disablePadding sx={{ mt: 0.5 }}>
            {trace.slice(0, 40).map((step, i) => {
                if (!isPlainObject(step)) {
                    return (
                        <ListItem key={i} disableGutters sx={{ py: 0.25 }}>
                            <ListItemText primaryTypographyProps={{ variant: "body2" }} primary={JSON.stringify(step)} />
                        </ListItem>
                    );
                }
                const sid = String(step.step_id ?? step.id ?? i);
                const title = String(step.title ?? step.name ?? sid);
                const status = step.status != null ? String(step.status) : "";
                return (
                    <ListItem key={sid + i} disableGutters sx={{ py: 0.35, alignItems: "flex-start" }}>
                        <ListItemText
                            primary={
                                <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                                    <Typography variant="body2" component="span">
                                        {title}
                                    </Typography>
                                    {status && <Chip size="small" label={humanizeKey(status)} variant="outlined" />}
                                </Stack>
                            }
                            secondary={step.last_error != null ? String(step.last_error) : undefined}
                            secondaryTypographyProps={{ color: "warning.main", variant: "caption" }}
                        />
                    </ListItem>
                );
            })}
            {trace.length > 40 && (
                <Typography variant="caption" color="text.secondary" sx={{ pl: 2 }}>
                    …and {trace.length - 40} more
                </Typography>
            )}
        </List>
    );
}

/** Heuristic friendly view for run event / conversation payloads. */
export function EventPayloadFriendly({ payload }: { payload: Record<string, unknown> }) {
    const tool = payload.tool != null ? String(payload.tool) : null;
    const args = payload.arguments ?? payload.args;
    const result = payload.result ?? payload.result_preview;
    const trace = Array.isArray(payload.trace) ? payload.trace : null;
    const flatScalars = Object.entries(payload).filter(
        ([k, v]) =>
            !["arguments", "args", "result", "result_preview", "trace", "payload"].includes(k) &&
            (typeof v === "string" || typeof v === "number" || typeof v === "boolean")
    );

    const hasStructured = tool || trace || (args !== undefined && isPlainObject(args as unknown)) || result !== undefined;

    return (
        <Stack spacing={1.25} sx={{ mt: 0.75 }}>
            {payload.error != null && (
                <Alert severity="error" variant="outlined">
                    {String(payload.error)}
                </Alert>
            )}
            {tool && (
                <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                    <Typography variant="caption" color="text.secondary">
                        Tool
                    </Typography>
                    <Chip size="small" label={tool} color="warning" variant="outlined" />
                </Stack>
            )}
            {flatScalars.length > 0 && (
                <Stack spacing={0.75}>
                    {flatScalars.map(([k, v]) => (
                        <ScalarLine key={k} label={humanizeKey(k)} value={v} />
                    ))}
                </Stack>
            )}
            {args !== undefined && (
                <Box>
                    <Typography variant="caption" color="text.secondary">
                        Arguments
                    </Typography>
                    {isPlainObject(args as unknown) ? (
                        <ShallowKeyValueList data={args as Record<string, unknown>} />
                    ) : (
                        <Typography variant="body2" sx={{ mt: 0.5, whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
                            {typeof args === "string" ? args : JSON.stringify(args, null, 2)}
                        </Typography>
                    )}
                </Box>
            )}
            {result !== undefined && (
                <Box>
                    <Typography variant="caption" color="text.secondary">
                        Result
                    </Typography>
                    <Typography variant="body2" sx={{ mt: 0.5, whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
                        {typeof result === "string"
                            ? result.length > 4000
                                ? `${result.slice(0, 4000)}…`
                                : result
                            : JSON.stringify(result, null, 2)}
                    </Typography>
                </Box>
            )}
            {trace && trace.length > 0 && (
                <Box>
                    <Typography variant="caption" color="text.secondary">
                        Workflow trace ({trace.length} steps)
                    </Typography>
                    <TraceStepsList trace={trace} />
                </Box>
            )}
            {!hasStructured && flatScalars.length === 0 && Object.keys(payload).length > 0 && (
                <ShallowKeyValueList data={payload} title="Details" />
            )}
            <CollapsibleRawJson value={payload} summary="Full event payload" />
        </Stack>
    );
}

function renderStructuredValue(value: unknown, depth = 0): ReactNode {
    if (value === null || value === undefined) {
        return (
            <Typography variant="body2" color="text.secondary">
                —
            </Typography>
        );
    }
    if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
        const s = String(value);
        return (
            <Typography variant="body2" sx={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
                {s.length > 6000 ? `${s.slice(0, 6000)}…` : s}
            </Typography>
        );
    }
    if (Array.isArray(value)) {
        if (value.every((x) => typeof x === "string" || typeof x === "number")) {
            return (
                <List dense disablePadding>
                    {value.map((item, i) => (
                        <ListItem key={i} disableGutters sx={{ py: 0.25, display: "list-item", pl: 2 }}>
                            <ListItemText primary={String(item)} primaryTypographyProps={{ variant: "body2" }} />
                        </ListItem>
                    ))}
                </List>
            );
        }
        if (depth >= 3) {
            return <CollapsibleRawJson value={value} defaultOpen={false} />;
        }
        return (
            <Stack spacing={1} sx={{ pl: depth > 0 ? 1 : 0, borderLeft: depth > 0 ? 1 : 0, borderColor: "divider" }}>
                {value.map((item, i) => (
                    <Box key={i}>{renderStructuredValue(item, depth + 1)}</Box>
                ))}
            </Stack>
        );
    }
    if (isPlainObject(value)) {
        if (depth >= 3) {
            return <CollapsibleRawJson value={value} defaultOpen={false} />;
        }
        const entries = Object.entries(value);
        return (
            <Stack spacing={1}>
                {entries.map(([k, v]) => (
                    <Box key={k}>
                        <Typography variant="caption" color="text.secondary">
                            {humanizeKey(k)}
                        </Typography>
                        <Box sx={{ mt: 0.25 }}>{renderStructuredValue(v, depth + 1)}</Box>
                    </Box>
                ))}
            </Stack>
        );
    }
    return <Typography variant="body2">{String(value)}</Typography>;
}

/** Main run output: plan, tools, structured JSON, prose — not one giant pre. */
export function RunOutputFriendly({ output }: { output: Record<string, unknown> }) {
    const plan = isPlainObject(output.plan) ? (output.plan as Record<string, unknown>) : null;
    const toolResults = Array.isArray(output.tool_results) ? output.tool_results : null;
    const structured = output.structured_output_json;
    const summary = output.summary != null ? String(output.summary) : null;
    const finalOut = output.final_output != null ? String(output.final_output) : null;

    const heuristic =
        isPlainObject(structured) &&
        (structured.local_heuristic === true || structured.provider === "local");

    const onCopyAll = useCallback(() => {
        copyToClipboard(JSON.stringify(output, null, 2));
    }, [output]);

    return (
        <Stack spacing={2.5}>
            <Stack direction="row" justifyContent="flex-end">
                <Button size="small" variant="outlined" startIcon={<ContentCopyIcon />} onClick={onCopyAll}>
                    Copy full output (JSON)
                </Button>
            </Stack>

            {heuristic && typeof structured === "object" && structured !== null && "stub_notice" in structured && (
                <Alert severity="info" variant="outlined">
                    {String((structured as Record<string, unknown>).stub_notice)}
                </Alert>
            )}

            {plan && (
                <Box>
                    <Typography variant="subtitle2" gutterBottom>
                        Execution plan
                    </Typography>
                    {plan.summary != null && (
                        <Typography variant="body2" color="text.secondary" sx={{ whiteSpace: "pre-wrap", mb: 1 }}>
                            {String(plan.summary).length > 8000 ? `${String(plan.summary).slice(0, 8000)}…` : String(plan.summary)}
                        </Typography>
                    )}
                    <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                        {Array.isArray(plan.tool_calls) && (
                            <Chip size="small" variant="outlined" label={`Planned tools: ${plan.tool_calls.length}`} />
                        )}
                        {Array.isArray(plan.sub_tasks) && (
                            <Chip size="small" variant="outlined" label={`Sub-tasks: ${plan.sub_tasks.length}`} />
                        )}
                    </Stack>
                    <CollapsibleRawJson value={plan} summary="Plan object (raw)" />
                </Box>
            )}

            {toolResults && toolResults.length > 0 && (
                <Box>
                    <Typography variant="subtitle2" gutterBottom>
                        Tool results
                    </Typography>
                    <Stack spacing={1}>
                        {toolResults.map((tr, i) => {
                            if (!isPlainObject(tr)) {
                                return (
                                    <Typography key={i} variant="body2">
                                        {JSON.stringify(tr)}
                                    </Typography>
                                );
                            }
                            const name = String(tr.tool ?? "tool");
                            const status = String(tr.status ?? "unknown");
                            return (
                                <Paper key={i} variant="outlined" sx={{ p: 1.25, borderRadius: 1 }}>
                                    <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 0.5 }}>
                                        <Typography variant="body2" fontWeight={600}>
                                            {name}
                                        </Typography>
                                        <Chip
                                            size="small"
                                            label={humanizeKey(status)}
                                            color={status === "completed" ? "success" : status === "failed" ? "error" : "default"}
                                            variant="outlined"
                                        />
                                    </Stack>
                                    {tr.error != null && (
                                        <Alert severity="warning" sx={{ my: 0.5 }}>
                                            {String(tr.error)}
                                        </Alert>
                                    )}
                                    {tr.result !== undefined && (
                                        <Typography variant="body2" sx={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
                                            {typeof tr.result === "string"
                                                ? tr.result
                                                : JSON.stringify(tr.result, null, 2)}
                                        </Typography>
                                    )}
                                </Paper>
                            );
                        })}
                    </Stack>
                </Box>
            )}

            {structured !== undefined && structured !== null && (
                <Box>
                    <Typography variant="subtitle2" gutterBottom>
                        Structured output
                    </Typography>
                    <Paper variant="outlined" sx={{ p: 1.5, borderRadius: 1 }}>
                        {renderStructuredValue(structured)}
                    </Paper>
                </Box>
            )}

            {summary && (!finalOut || summary !== finalOut) && (
                <Box>
                    <Typography variant="subtitle2" gutterBottom>
                        Summary
                    </Typography>
                    <Typography variant="body2" sx={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
                        {summary.length > 12000 ? `${summary.slice(0, 12000)}…` : summary}
                    </Typography>
                </Box>
            )}

            {finalOut && (
                <Box>
                    <Typography variant="subtitle2" gutterBottom>
                        Final text
                    </Typography>
                    <Typography variant="body2" sx={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
                        {finalOut.length > 12000 ? `${finalOut.slice(0, 12000)}…` : finalOut}
                    </Typography>
                </Box>
            )}

            <Divider />
            <CollapsibleRawJson value={output} summary="Complete output_payload (raw)" />
        </Stack>
    );
}

/** Top-level checkpoint keys as chips + raw JSON collapsed. */
export function CheckpointFriendlySummary({ checkpoint }: { checkpoint: Record<string, unknown> }) {
    const keys = Object.keys(checkpoint);
    if (keys.length === 0) {
        return <Typography variant="body2" color="text.secondary">Empty checkpoint.</Typography>;
    }
    return (
        <Stack spacing={1}>
            <Typography variant="caption" color="text.secondary">
                Checkpoint sections
            </Typography>
            <Stack direction="row" flexWrap="wrap" gap={0.5} useFlexGap>
                {keys.map((k) => (
                    <Chip key={k} size="small" label={humanizeKey(k)} variant="outlined" />
                ))}
            </Stack>
            <CollapsibleRawJson value={checkpoint} defaultOpen={false} maxHeight={360} />
        </Stack>
    );
}
