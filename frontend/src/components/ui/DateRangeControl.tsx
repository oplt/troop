import { MenuItem, TextField } from "@mui/material";

export const ANALYTICS_DAY_OPTIONS = [7, 14, 30, 90] as const;
export type AnalyticsDays = (typeof ANALYTICS_DAY_OPTIONS)[number];

type DateRangeControlProps = {
    value: number;
    onChange: (days: number) => void;
    label?: string;
    options?: readonly number[];
    size?: "small" | "medium";
};

/** Shared analytics / insights window control. */
export function DateRangeControl({
    value,
    onChange,
    label = "Window",
    options = ANALYTICS_DAY_OPTIONS,
    size = "small",
}: DateRangeControlProps) {
    return (
        <TextField
            select
            label={label}
            size={size}
            value={value}
            onChange={(event) => onChange(Number(event.target.value))}
            sx={{ minWidth: 180 }}
            inputProps={{ "aria-label": label }}
        >
            {options.map((days) => (
                <MenuItem key={days} value={days}>
                    Last {days} days
                </MenuItem>
            ))}
        </TextField>
    );
}
