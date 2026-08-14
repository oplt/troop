import { formatCurrency } from "../../utils/formatters";

export function formatCostMicros(micros: number) {
    return formatCurrency(micros / 10000, "USD");
}

export function parseVariableDefinitions(rawNames: string) {
    return rawNames
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean)
        .map((name) => ({ name, description: null, required: true }));
}
