import {
    Alert,
    Box,
    Button,
    Chip,
    IconButton,
    MenuItem,
    Stack,
    TextField,
    Typography,
} from "@mui/material";
import { DeleteOutline as DeleteIcon } from "@mui/icons-material";

import type { DatabaseSetting, ParameterCatalogEntry } from "../../../api/settings";
import { formatDateTime } from "../../../utils/formatters";
import type { DatabaseSettingDraft } from "../types";
import { databaseEditorSx } from "../styles";

type DatabaseSettingEditorProps = {
    item: DatabaseSetting;
    draft: DatabaseSettingDraft;
    spec: ParameterCatalogEntry | null;
    onDraftChange: (nextDraft: DatabaseSettingDraft) => void;
    onSave: () => void;
    onDelete: () => void;
    isSaving: boolean;
    isDeleting: boolean;
};

export function DatabaseSettingEditor({
    item,
    draft,
    spec,
    onDraftChange,
    onSave,
    onDelete,
    isSaving,
    isDeleting,
}: DatabaseSettingEditorProps) {
    const valueType = spec?.value_type ?? "string";
    const isKnown = Boolean(spec);

    return (
        <Box sx={databaseEditorSx}>
            <Stack spacing={1.5}>
                <Stack direction="row" justifyContent="space-between" spacing={1.5}>
                    <Box>
                        <Typography variant="subtitle2">{item.key}</Typography>
                        <Typography variant="caption" color="text.secondary">
                            Updated {formatDateTime(item.updated_at)}
                        </Typography>
                    </Box>
                    <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                        <Chip label={valueType} size="small" variant="outlined" />
                        {!isKnown && <Chip label="unknown" size="small" color="warning" variant="outlined" />}
                    </Stack>
                    <IconButton color="error" onClick={onDelete} disabled={isDeleting}>
                        <DeleteIcon />
                    </IconButton>
                </Stack>

                <TextField
                    label="Value"
                    value={draft.value}
                    onChange={(event) =>
                        onDraftChange({ value: event.target.value, description: draft.description })
                    }
                    select={valueType === "bool"}
                    fullWidth
                    multiline={valueType === "json"}
                    minRows={valueType === "json" ? 3 : undefined}
                >
                    {valueType === "bool"
                        ? [
                              <MenuItem key="true" value="true">
                                  true
                              </MenuItem>,
                              <MenuItem key="false" value="false">
                                  false
                              </MenuItem>,
                          ]
                        : null}
                </TextField>

                {spec?.description ? (
                    <Typography variant="caption" color="text.secondary">
                        {spec.description}
                    </Typography>
                ) : null}

                {!isKnown ? (
                    <Alert severity="warning">
                        Unknown parameter key. This row is legacy/custom and not in catalog.
                    </Alert>
                ) : null}

                {valueType === "int" ? (
                    <Typography variant="caption" color="text.secondary">
                        Enter integer value.
                    </Typography>
                ) : null}

                {valueType === "json" ? (
                    <Typography variant="caption" color="text.secondary">
                        Enter valid JSON object/array text.
                    </Typography>
                ) : null}

                <TextField
                    label="Description"
                    value={draft.description}
                    onChange={(event) =>
                        onDraftChange({
                            value: draft.value,
                            description: event.target.value,
                        })
                    }
                    fullWidth
                    multiline
                    minRows={3}
                />

                <Button variant="contained" disabled={isSaving} onClick={onSave}>
                    {isSaving ? "Saving..." : "Save parameter"}
                </Button>
            </Stack>
        </Box>
    );
}
