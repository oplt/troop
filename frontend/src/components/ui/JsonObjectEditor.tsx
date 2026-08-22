import { useMemo, useState } from "react";
import { TextField } from "@mui/material";

import { jsonObjectValidationError } from "./jsonObjectValidation";

type JsonObjectEditorProps = {
    label: string;
    value: string;
    onChange: (value: string) => void;
    minRows?: number;
    allowEmpty?: boolean;
    helperText?: string;
};

/** Consistent object-only JSON editing with inline validation. */
export function JsonObjectEditor({
    label,
    value,
    onChange,
    minRows = 5,
    allowEmpty = false,
    helperText,
}: JsonObjectEditorProps) {
    const [touched, setTouched] = useState(false);
    const validationError = useMemo(
        () => jsonObjectValidationError(value, allowEmpty),
        [allowEmpty, value],
    );
    return (
        <TextField
            label={label}
            value={value}
            onChange={(event) => onChange(event.target.value)}
            onBlur={() => setTouched(true)}
            fullWidth
            multiline
            minRows={minRows}
            error={touched && Boolean(validationError)}
            helperText={touched && validationError ? validationError : helperText}
            inputProps={{ spellCheck: false }}
        />
    );
}
