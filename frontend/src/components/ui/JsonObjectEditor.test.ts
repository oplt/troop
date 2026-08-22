import { describe, expect, it } from "vitest";

import { jsonObjectValidationError } from "./jsonObjectValidation";

describe("jsonObjectValidationError", () => {
    it("accepts objects and rejects arrays or malformed input", () => {
        expect(jsonObjectValidationError('{"ok":true}')).toBeNull();
        expect(jsonObjectValidationError("[]")).toBe("JSON value must be an object.");
        expect(jsonObjectValidationError("{")).toBe("Enter valid JSON.");
        expect(jsonObjectValidationError("", true)).toBeNull();
    });
});
