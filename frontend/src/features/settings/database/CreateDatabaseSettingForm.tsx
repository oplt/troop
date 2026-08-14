import { Alert, Button, MenuItem, Stack, TextField, Typography } from "@mui/material";

import type { ParameterCatalogEntry } from "../../../api/settings";
import type { NewDatabaseSettingForm } from "../types";

type CreateDatabaseSettingFormProps = {
    form: NewDatabaseSettingForm;
    parameterCatalog: ParameterCatalogEntry[];
    selectedSpec: ParameterCatalogEntry | null;
    isCreating: boolean;
    createSucceeded: boolean;
    createError: unknown;
    onFormChange: (updater: (current: NewDatabaseSettingForm) => NewDatabaseSettingForm) => void;
    onCreate: () => void;
};

export function CreateDatabaseSettingForm({
    form,
    parameterCatalog,
    selectedSpec,
    isCreating,
    createSucceeded,
    createError,
    onFormChange,
    onCreate,
}: CreateDatabaseSettingFormProps) {
    return (
        <Stack spacing={2}>
            {createSucceeded && <Alert severity="success">Parameter created.</Alert>}
            {createError ? (
                <Alert severity="error">
                    {createError instanceof Error ? createError.message : "Couldn't save parameter. Try again."}
                </Alert>
            ) : null}

            <TextField
                label="Key"
                value={form.key}
                onChange={(event) => {
                    const key = event.target.value;
                    const spec = parameterCatalog.find((entry) => entry.key === key) ?? null;
                    onFormChange((current) => ({
                        ...current,
                        key,
                        value: spec ? spec.default_value : "",
                        description: spec?.description ?? current.description,
                    }));
                }}
                select
                fullWidth
            >
                {parameterCatalog.map((entry) => (
                    <MenuItem key={entry.key} value={entry.key}>
                        {entry.key}
                    </MenuItem>
                ))}
            </TextField>

            <TextField
                label="Value"
                value={form.value}
                onChange={(event) => onFormChange((current) => ({ ...current, value: event.target.value }))}
                fullWidth
                select={selectedSpec?.value_type === "bool"}
                multiline={selectedSpec?.value_type === "json"}
                minRows={selectedSpec?.value_type === "json" ? 3 : undefined}
            >
                {selectedSpec?.value_type === "bool"
                    ? [
                          <MenuItem key="new-true" value="true">
                              true
                          </MenuItem>,
                          <MenuItem key="new-false" value="false">
                              false
                          </MenuItem>,
                      ]
                    : null}
            </TextField>

            {selectedSpec ? (
                <Typography variant="caption" color="text.secondary">
                    Type: {selectedSpec.value_type}. {selectedSpec.description}
                </Typography>
            ) : null}

            <TextField
                label="Description"
                value={form.description}
                onChange={(event) => onFormChange((current) => ({ ...current, description: event.target.value }))}
                fullWidth
                multiline
                minRows={3}
            />

            <Button variant="contained" disabled={isCreating || !form.key.trim()} onClick={onCreate}>
                {isCreating ? "Adding..." : "Add parameter"}
            </Button>
        </Stack>
    );
}
