import { expect, test } from "@playwright/test";
import { apiSignIn, seedFixture } from "./helpers/api";
import { login } from "./helpers/auth";
import { readCredentials } from "./helpers/credentials";

test("connector reauthorization_required surfaces on integrations page", async ({ page, request }) => {
    const credentials = readCredentials();
    await apiSignIn(request, credentials.email, credentials.password);
    seedFixture("reauth-connector", credentials.userId);

    await login(page, credentials);
    await page.goto("/integrations");

    await expect(page.getByRole("heading", { name: "Integrations" })).toBeVisible();
    await expect(page.getByText(/reauthorization required|Reauthorization Required/i)).toBeVisible({
        timeout: 30_000,
    });
    await expect(page.getByText(/reconnect|OAuth token expired/i)).toBeVisible({ timeout: 15_000 });
});
