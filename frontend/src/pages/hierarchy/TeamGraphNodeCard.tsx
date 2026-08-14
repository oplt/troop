import { Box, Chip, Divider, Paper, Stack, Typography } from "@mui/material";
import { alpha, useTheme } from "@mui/material/styles";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { getCanvasTheme } from "../../features/canvas/canvasTheme";
import type { TeamGraphNode } from "./hierarchyTypes";
import { getRoleIcon } from "./hierarchyGraphUtils";

export function TeamGraphNodeCard({ data, selected }: NodeProps<TeamGraphNode>) {
    const theme = useTheme();
    const canvas = getCanvasTheme(theme);
    const tone = data.role === "manager" ? "#175cd3" : data.role === "reviewer" ? "#b26a00" : "#087443";
    const statusDotColor =
        data.status === "running" || data.status === "active"
            ? "#12b76a"
            : data.status === "blocked"
                ? "#f79009"
                : data.status === "queued"
                    ? "#667085"
                    : data.status === "draft"
                        ? "#9e77ed"
                        : canvas.idleStatusDot;
    const isPulsing = data.status === "running";
    const hiddenCaps = Math.max(0, data.capabilities.length - 2);

    return (
        <Paper
            elevation={0}
            sx={{
                width: 284,
                borderRadius: 1,
                border: "2px solid",
                borderColor: selected ? "primary.main" : "divider",
                bgcolor: data.status === "inactive" ? "grey.50" : "background.paper",
                boxShadow: "none",
                transition: "border-color 0.33s, background-color 0.33s",
                opacity: data.status === "inactive" ? 0.75 : 1,
                overflow: "hidden",
                position: "relative",
                "&:hover": {
                    backgroundColor: "grey.50",
                },
            }}
        >
            <Handle
                type="target"
                position={Position.Top}
                style={{ background: tone, width: 10, height: 10, border: "2px solid white" }}
            />
            <Box
                sx={{
                    position: "absolute",
                    left: 0,
                    top: 0,
                    bottom: 0,
                    width: 4,
                    bgcolor: tone,
                }}
            />
            <Box
                sx={{
                    px: 1.75,
                    pt: 1.5,
                    pb: 1.1,
                    bgcolor: alpha(tone, 0.08),
                }}
            >
                <Stack direction="row" alignItems="center" justifyContent="space-between" spacing={1}>
                    <Stack direction="row" spacing={1.25} alignItems="center" sx={{ minWidth: 0 }}>
                        <Box
                            sx={{
                                width: 38,
                                height: 38,
                                borderRadius: 1,
                                display: "grid",
                                placeItems: "center",
                                bgcolor: alpha(tone, 0.12),
                                color: tone,
                                border: `1px solid ${alpha(tone, 0.22)}`,
                            }}
                        >
                            {getRoleIcon(data.role)}
                        </Box>
                        <Box sx={{ minWidth: 0 }}>
                            <Typography variant="subtitle2" fontWeight={500} noWrap>
                                {data.name || "Untitled agent"}
                            </Typography>
                            <Typography
                                variant="caption"
                                color="text.secondary"
                                sx={{ fontFamily: "IBM Plex Mono, monospace", display: "block" }}
                                noWrap
                            >
                                {data.subtitle || data.slug || data.role}
                            </Typography>
                        </Box>
                    </Stack>
                    <Stack direction="row" alignItems="center" spacing={0.6}>
                        <Box
                            sx={{
                                width: 8,
                                height: 8,
                                borderRadius: "50%",
                                bgcolor: statusDotColor,
                                boxShadow: isPulsing ? `0 0 0 2px ${alpha(statusDotColor, 0.2)}` : "none",
                                animation: isPulsing ? "troop-pulse 1.4s ease-in-out infinite" : "none",
                                "@keyframes troop-pulse": {
                                    "0%, 100%": { opacity: 1 },
                                    "50%": { opacity: 0.5 },
                                },
                            }}
                        />
                        <Typography
                            variant="caption"
                            sx={{
                                fontWeight: 500,
                                color: "text.secondary",
                            }}
                        >
                            {data.status}
                        </Typography>
                    </Stack>
                </Stack>
            </Box>

            <Stack spacing={1} sx={{ px: 1.75, pb: 1.5, pt: 1.25 }}>
                <Typography variant="body2" color="text.secondary" sx={{ minHeight: 36, lineHeight: 1.45 }}>
                    {data.description || "No contract description yet."}
                </Typography>

                {data.model ? (
                    <Stack direction="row" spacing={0.75} alignItems="center">
                        <Typography
                            variant="caption"
                            sx={{ fontWeight: 500, color: "text.secondary" }}
                        >
                            model
                        </Typography>
                        <Typography
                            variant="caption"
                            sx={{ fontFamily: "IBM Plex Mono, monospace", color: "text.primary" }}
                            noWrap
                        >
                            {data.model}
                        </Typography>
                    </Stack>
                ) : null}

                <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
                    <Chip
                        size="small"
                        label={data.role}
                        sx={{
                            height: 22,
                            bgcolor: alpha(tone, 0.12),
                            color: tone,
                            fontWeight: 500,
                            textTransform: "capitalize",
                            border: `1px solid ${alpha(tone, 0.25)}`,
                        }}
                    />
                    {data.capabilities.slice(0, 2).map((item) => (
                        <Chip
                            key={`${data.slug}-${item}`}
                            size="small"
                            label={item}
                            variant="outlined"
                            sx={{ height: 22 }}
                        />
                    ))}
                    {hiddenCaps > 0 ? (
                        <Chip size="small" label={`+${hiddenCaps}`} variant="outlined" sx={{ height: 22 }} />
                    ) : null}
                </Stack>

                {(data.allowedTools.length > 0 ||
                    data.projectAssignments.length > 0 ||
                    data.tags.length > 0) && (
                    <>
                        <Divider flexItem sx={{ borderStyle: "dashed", opacity: 0.6 }} />
                        <Stack
                            direction="row"
                            spacing={1.5}
                            sx={{ color: "text.secondary", fontSize: 11 }}
                            divider={<Box sx={{ width: "1px", bgcolor: alpha("#101828", 0.1) }} />}
                        >
                            {data.allowedTools.length > 0 ? (
                                <Typography variant="caption">
                                    <Box component="strong" sx={{ color: "text.primary" }}>
                                        {data.allowedTools.length}
                                    </Box>{" "}
                                    tools
                                </Typography>
                            ) : null}
                            {data.projectAssignments.length > 0 ? (
                                <Typography variant="caption">
                                    <Box component="strong" sx={{ color: "text.primary" }}>
                                        {data.projectAssignments.length}
                                    </Box>{" "}
                                    projects
                                </Typography>
                            ) : null}
                            {data.tags.length > 0 ? (
                                <Typography variant="caption">
                                    <Box component="strong" sx={{ color: "text.primary" }}>
                                        {data.tags.length}
                                    </Box>{" "}
                                    tags
                                </Typography>
                            ) : null}
                        </Stack>
                    </>
                )}
            </Stack>
            <Handle
                type="source"
                position={Position.Bottom}
                style={{ background: tone, width: 10, height: 10, border: "2px solid white" }}
            />
        </Paper>
    );
}

