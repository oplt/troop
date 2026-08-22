export function jsonObjectValidationError(value: string, allowEmpty = false): string | null {
    if (!value.trim()) return allowEmpty ? null : "Enter a JSON object.";
    try {
        const parsed = JSON.parse(value) as unknown;
        return parsed && typeof parsed === "object" && !Array.isArray(parsed)
            ? null
            : "JSON value must be an object.";
    } catch {
        return "Enter valid JSON.";
    }
}
