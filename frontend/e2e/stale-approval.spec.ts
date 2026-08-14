import { expect, test } from "@playwright/test";
import { apiSignIn, seedFixture } from "./helpers/api";
import { login } from "./helpers/auth";
import { readCredentials } from "./helpers/credentials";

test("stale approval cannot be approved from the UI", async ({ page, request }) => {
    const credentials = readCredentials();
    await apiSignIn(request, credentials.email, credentials.password);
    seedFixture("stale-approval", credentials.userId);

    await login(page, credentials);
    await page.goto("/approvals");

    const approveButton = page.getByRole("button", { name: "Approve", exact: true }).first();
    await expect(approveButton).toBeVisible({ timeout: 30_000 });
    await approveButton.click();
    await expect(page.getByText(/stale|expired|couldn't save/i)).toBeVisible({ timeout: 15_000 });
});
