import { MenuItem, TextField } from "@mui/material";
import { humanizeKey } from "../../utils/formatters";
import { schemaProperties, schemaRequiredKeys } from "./manifestUtils";

type JsonSchema = Record<string, unknown>;

const HIDDEN_FIELDS = new Set(["connector_installation_id"]);

function fieldType(property: JsonSchema): string {
    if (Array.isArray(property.type)) {
        return String(property.type.find((item) => item !== "null") ?? "string");
    }
    return String(property.type ?? "string");
}

function isSecretField(key: string, property: JsonSchema): boolean {
    return /(token|secret|password|api_key)/i.test(key) || property.format === "password";
}

export function JsonSchemaFields({
    schema,
    values,
    onChange,
    exclude = [],
    size = "small",
}: {
    schema: JsonSchema;
    values: Record<string, unknown>;
    onChange: (key: string, value: unknown) => void;
    exclude?: string[];
    size?: "small" | "medium";
}) {
    const properties = schemaProperties(schema);
    const required = schemaRequiredKeys(schema);
    const hidden = new Set([...HIDDEN_FIELDS, ...exclude]);
    const entries = Object.entries(properties).filter(([key]) => !hidden.has(key));
    if (!entries.length) return null;

    return (
        <>
            {entries.map(([key, property]) => {
                const type = fieldType(property);
                const label = String(property.title ?? humanizeKey(key));
                const helperText = typeof property.description === "string" ? property.description : undefined;
                const example = Array.isArray(property.examples) ? property.examples[0] : undefined;
                const value = values[key];

                if (type === "boolean") {
                    return (
                        <TextField
                            key={key}
                            select
                            label={label}
                            value={String(Boolean(value))}
                            onChange={(event) => onChange(key, event.target.value === "true")}
                            helperText={helperText}
                            required={required.has(key)}
                            fullWidth
                            size={size}
                        >
                            <MenuItem value="true">True</MenuItem>
                            <MenuItem value="false">False</MenuItem>
                        </TextField>
                    );
                }

                if (type === "integer" || type === "number") {
                    return (
                        <TextField
                            key={key}
                            type="number"
                            label={label}
                            value={value === undefined || value === null ? "" : String(value)}
                            onChange={(event) => onChange(key, event.target.value === "" ? undefined : Number(event.target.value))}
                            helperText={helperText}
                            required={required.has(key)}
                            fullWidth
                            size={size}
                            inputProps={{
                                min: typeof property.minimum === "number" ? property.minimum : undefined,
                                max: typeof property.maximum === "number" ? property.maximum : undefined,
                            }}
                        />
                    );
                }

                if (type === "array") {
                    return (
                        <TextField
                            key={key}
                            label={label}
                            value={Array.isArray(value) ? value.join(", ") : String(value ?? "")}
                            onChange={(event) => {
                                const next = event.target.value
                                    .split(",")
                                    .map((item) => item.trim())
                                    .filter(Boolean);
                                onChange(key, next);
                            }}
                            helperText={helperText ?? "Comma-separated values or JSONPath expressions."}
                            required={required.has(key)}
                            fullWidth
                            size={size}
                        />
                    );
                }

                return (
                    <TextField
                        key={key}
                        label={label}
                        value={value === undefined || value === null ? "" : String(value)}
                        onChange={(event) => onChange(key, event.target.value)}
                        helperText={helperText ?? (String(example ?? "").includes("$") ? "Literal value or JSONPath such as $.email.thread_id" : undefined)}
                        required={required.has(key)}
                        fullWidth
                        size={size}
                        type={isSecretField(key, property) ? "password" : "text"}
                        autoComplete={isSecretField(key, property) ? "off" : undefined}
                        multiline={Boolean(property.multiline) || String(property.format) === "textarea"}
                        minRows={property.multiline ? 2 : undefined}
                    />
                );
            })}
        </>
    );
}
