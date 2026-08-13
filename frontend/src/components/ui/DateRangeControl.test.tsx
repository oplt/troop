import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DateRangeControl } from "./DateRangeControl";

describe("DateRangeControl", () => {
    it("emits selected day window", async () => {
        const user = userEvent.setup();
        const onChange = vi.fn();
        render(<DateRangeControl value={7} onChange={onChange} />);
        await user.click(screen.getByLabelText("Window"));
        await user.click(await screen.findByRole("option", { name: "Last 30 days" }));
        expect(onChange).toHaveBeenCalledWith(30);
    });
});
