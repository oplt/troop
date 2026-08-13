import { Stack, type SxProps, type Theme } from "@mui/material";

type FormFieldStackProps = {
    children: React.ReactNode;
    sx?: SxProps<Theme>;
};

/**
 * Standard form field density: tight vertical rhythm, full-width fields.
 * Pair with size="small" TextFields and helperText under the control.
 */
export function FormFieldStack({ children, sx }: FormFieldStackProps) {
    return (
        <Stack
            spacing={2}
            sx={[
                {
                    "& .MuiFormHelperText-root": { mx: 0 },
                    "& .MuiTextField-root": { width: "100%" },
                },
                ...(Array.isArray(sx) ? sx : sx ? [sx] : []),
            ]}
        >
            {children}
        </Stack>
    );
}
