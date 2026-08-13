import { Chip, type ChipProps } from "@mui/material";
import {
    Cancel as CancelIcon,
    CheckCircleOutline as SuccessIcon,
    ErrorOutline as ErrorIcon,
    HourglassEmpty as PendingIcon,
    PauseCircleOutline as PausedIcon,
    PlayArrow as RunningIcon,
    Schedule as QueuedIcon,
} from "@mui/icons-material";
import { humanizeKey } from "../../utils/formatters";
import { resolveStatusTone, type StatusKind, type StatusTone } from "./statusTokens";

function statusIcon(status: string, tone: StatusTone) {
    const key = status.trim().toLowerCase().replace(/\s+/g, "_");
    if (key === "queued" || key === "pending" || key === "awaiting") {
        return <QueuedIcon fontSize="small" />;
    }
    if (key === "in_progress" || key === "running") {
        return <RunningIcon fontSize="small" />;
    }
    if (key === "paused") {
        return <PausedIcon fontSize="small" />;
    }
    if (key === "cancelled" || key === "canceled") {
        return <CancelIcon fontSize="small" />;
    }
    if (tone === "success") {
        return <SuccessIcon fontSize="small" />;
    }
    if (tone === "error") {
        return <ErrorIcon fontSize="small" />;
    }
    if (tone === "warning") {
        return <PendingIcon fontSize="small" />;
    }
    return undefined;
}

type StatusChipProps = {
    status: string;
    kind?: StatusKind;
    label?: string;
    size?: ChipProps["size"];
    variant?: ChipProps["variant"];
    /** Show leading status icon. Default true. */
    showIcon?: boolean;
    className?: string;
    /** Apply success flash when status becomes approved/completed. */
    celebrate?: boolean;
};

export function StatusChip({
    status,
    kind = "generic",
    label,
    size = "small",
    variant = "outlined",
    showIcon = true,
    className,
    celebrate = false,
}: StatusChipProps) {
    const tone = resolveStatusTone(status, kind);
    const icon = showIcon ? statusIcon(status, tone) : undefined;
    const flash = celebrate && tone === "success" ? "troop-success-flash" : undefined;
    return (
        <Chip
            className={[className, flash].filter(Boolean).join(" ") || undefined}
            size={size}
            variant={variant}
            color={tone === "default" ? "default" : tone}
            icon={icon}
            label={label ?? humanizeKey(status)}
        />
    );
}
