import { useMemo, useState } from "react";
import {
    Alert,
    Box,
    Button,
    Chip,
    Collapse,
    IconButton,
    Paper,
    Stack,
    ToggleButton,
    ToggleButtonGroup,
    Typography,
} from "@mui/material";
import { alpha } from "@mui/material/styles";
import { ExpandLess, ExpandMore } from "@mui/icons-material";
import type { RunTraceSpan } from "../../api/orchestration";
import { CollapsibleRawJson } from "../../components/runInspector/RunInspectorDataViews";
import { formatDateTime, humanizeKey } from "../../utils/formatters";
import { filterTraceSpans, spanKindLabel, type RunTraceFilter } from "./traceUtils";

const FILTERS: Array<{ value: RunTraceFilter; label: string }> = [
    { value: "all", label: "All" },
    { value: "models", label: "Models" },
    { value: "tools", label: "Tools" },
    { value: "approvals", label: "Approvals" },
    { value: "errors", label: "Errors" },
    { value: "memory", label: "Memory" },
    { value: "retries", label: "Retries" },
];

function spanStatusColor(status: string): "success" | "error" | "warning" | "info" | "default" {
    if (status === "completed") return "success";
    if (status === "failed" || status === "rejected") return "error";
    if (status === "blocked" || status === "pending" || status === "waiting") return "warning";
    if (status === "started" || status === "running" || status === "in_progress") return "info";
    return "default";
}

function RunTraceSpanRow({ span, index }: { span: RunTraceSpan; index: number }) {
    const [open, setOpen] = useState(false);
    const isExternalEffect = span.kind === "tool_effect" && (
        span.id.startsWith("effect:")
        || Boolean(span.safe_payload.external_result_id)
        || Boolean(span.safe_payload.action_key)
    );
    const isRetry = span.kind === "retry_checkpoint";

    return (
        <Paper
            variant="outlined"
            sx={(theme) => ({
                p: 1.5,
                borderRadius: 1,
                borderLeft: `3px solid ${
                    isRetry
                        ? theme.palette.warning.main
                        : isExternalEffect
                          ? theme.palette.secondary.main
                          : theme.palette.divider
                }`,
                bgcolor: isExternalEffect ? alpha(theme.palette.secondary.main, 0.04) : undefined,
            })}
        >
            <Stack direction="row" spacing={1.5} alignItems="flex-start">
                <Typography variant="caption" color="text.disabled" sx={{ fontFamily: "monospace", minWidth: 28, pt: 0.3 }}>
                    #{index + 1}
                </Typography>
                <Box flex={1}>
                    <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                        <Chip label={humanizeKey(spanKindLabel(span.kind))} size="small" variant="outlined" />
                        <Chip label={humanizeKey(span.status)} size="small" color={spanStatusColor(span.status)} />
                        {isRetry && <Chip label="Retry / checkpoint" size="small" color="warning" variant="outlined" />}
                        {isExternalEffect && (
                            <Chip label="External effect receipt" size="small" color="secondary" variant="outlined" />
                        )}
                        <Typography variant="subtitle2" sx={{ flex: 1 }}>{span.title}</Typography>
                        <Typography variant="caption" color="text.secondary" sx={{ whiteSpace: "nowrap" }}>
                            {formatDateTime(span.started_at)}
                        </Typography>
                        <IconButton size="small" onClick={() => setOpen((value) => !value)} sx={{ p: 0.25 }}>
                            {open ? <ExpandLess fontSize="small" /> : <ExpandMore fontSize="small" />}
                        </IconButton>
                    </Stack>
                    {span.message && (
                        <Typography variant="body2" color="text.secondary" sx={{ mt: 0.75 }}>
                            {span.message}
                        </Typography>
                    )}
                    {isExternalEffect && (
                        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mt: 1 }}>
                            {Boolean(span.safe_payload.external_result_id) && (
                                <Chip
                                    size="small"
                                    variant="outlined"
                                    label={`Receipt ${String(span.safe_payload.external_result_id).slice(0, 24)}`}
                                />
                            )}
                            {Boolean(span.safe_payload.action_key) && (
                                <Chip size="small" variant="outlined" label={String(span.safe_payload.action_key)} />
                            )}
                            {Boolean(span.safe_payload.status) && (
                                <Chip size="small" variant="outlined" label={String(span.safe_payload.status)} />
                            )}
                        </Stack>
                    )}
                    <Collapse in={open}>
                        <Stack spacing={1} sx={{ mt: 1 }}>
                            {(span.tokens_input > 0 || span.tokens_output > 0) && (
                                <Typography variant="caption" color="text.secondary">
                                    Tokens {span.tokens_input} in / {span.tokens_output} out
                                    {span.cost_usd_micros > 0 ? ` · $${(span.cost_usd_micros / 1_000_000).toFixed(5)}` : ""}
                                </Typography>
                            )}
                            {span.restricted.has_restricted && (
                                <Alert severity="info" sx={{ py: 0 }}>
                                    Restricted fields omitted: {span.restricted.restricted_fields.join(", ") || "raw payload"}
                                </Alert>
                            )}
                            {Object.keys(span.safe_payload).length > 0 && (
                                <CollapsibleRawJson value={span.safe_payload} summary="Safe payload" maxHeight={220} />
                            )}
                            {span.parent_span_id && (
                                <Typography variant="caption" color="text.secondary">
                                    Parent span: {span.parent_span_id}
                                </Typography>
                            )}
                        </Stack>
                    </Collapse>
                </Box>
            </Stack>
        </Paper>
    );
}

type RunTraceTimelineProps = {
    spans: RunTraceSpan[];
    truncated?: boolean;
    loading?: boolean;
    onLoadMore?: () => void;
    hasMore?: boolean;
};

export function RunTraceTimeline({
    spans,
    truncated,
    loading,
    onLoadMore,
    hasMore,
}: RunTraceTimelineProps) {
    const [filter, setFilter] = useState<RunTraceFilter>("all");
    const filtered = useMemo(() => filterTraceSpans(spans, filter), [spans, filter]);

    return (
        <Stack spacing={2}>
            <ToggleButtonGroup
                size="small"
                value={filter}
                exclusive
                onChange={(_, value: RunTraceFilter | null) => value && setFilter(value)}
                sx={{ flexWrap: "wrap" }}
            >
                {FILTERS.map((item) => (
                    <ToggleButton key={item.value} value={item.value}>
                        {item.label}
                    </ToggleButton>
                ))}
            </ToggleButtonGroup>

            {truncated && (
                <Alert severity="warning">Trace truncated — load more to see additional spans.</Alert>
            )}

            {filtered.length === 0 ? (
                <Typography variant="body2" color="text.secondary">
                    No spans match this filter.
                </Typography>
            ) : (
                <Stack spacing={1}>
                    {filtered.map((span, index) => (
                        <RunTraceSpanRow key={span.id} span={span} index={index} />
                    ))}
                </Stack>
            )}

            {hasMore && onLoadMore && (
                <Button variant="outlined" onClick={onLoadMore} disabled={loading}>
                    {loading ? "Loading…" : "Load more spans"}
                </Button>
            )}
        </Stack>
    );
}
