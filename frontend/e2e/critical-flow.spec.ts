import { expect, test } from "@playwright/test";
import { apiFetch, apiSignIn, seedFixture } from "./helpers/api";
import { login } from "./helpers/auth";
import { readCredentials } from "./helpers/credentials";

test.describe.configure({ mode: "serial" });

test.describe("critical flow", () => {
    test("login → fixture connector → workflow test → approve → resume → receipt", async ({
        page,
        request,
    }) => {
        const credentials = readCredentials();
        await apiSignIn(request, credentials.email, credentials.password);
        const scenario = seedFixture("critical-flow", credentials.userId);
        const workflowName = String(scenario.workflowName);
        const fixtureInput = scenario.fixtureInput as Record<string, unknown>;

        await login(page, credentials);

        await page.goto("/integrations");
        await expect(page.getByRole("heading", { name: "Integrations" })).toBeVisible();
        await expect(page.getByText("Telegram", { exact: false }).first()).toBeVisible();

        await page.goto("/workforce-workflows");
        await expect(page.getByRole("heading", { name: "Workforce workflows" })).toBeVisible();

        const workflowRow = page.locator(".MuiPaper-root").filter({ hasText: workflowName });
        await workflowRow.getByRole("button", { name: "Load" }).click();
        await expect(page.getByText(`Loaded ${workflowName}`)).toBeVisible({ timeout: 15_000 });

        await page.getByRole("tab", { name: "Test" }).click();
        await page.getByLabel("Test fixture (JSON input)").fill(JSON.stringify(fixtureInput));
        await page.getByRole("button", { name: "Test run draft" }).click();
        await expect(page.getByText(/Test run .* started/i)).toBeVisible({ timeout: 30_000 });

        await page.goto("/approvals");
        await expect(page.getByRole("heading", { name: "Approvals" })).toBeVisible();
        const approveButton = page.getByRole("button", { name: "Approve", exact: true }).first();
        await expect(approveButton).toBeVisible({ timeout: 30_000 });
        await approveButton.click();
        await expect(page.getByText(/Approval saved/i)).toBeVisible({ timeout: 30_000 });

        await page.goto("/workforce-workflows");
        await expect(page.getByText(/succeeded|completed/i).first()).toBeVisible({ timeout: 60_000 });
        await expect(page.getByText("playwright-e2e", { exact: false })).toBeVisible({ timeout: 60_000 });
    });

    test("reject pending approval with reason", async ({ page, request }) => {
        const credentials = readCredentials();
        const session = await apiSignIn(request, credentials.email, credentials.password);
        const scenario = seedFixture("critical-flow", credentials.userId);
        const fixtureInput = scenario.fixtureInput as Record<string, unknown>;

        await apiFetch(session, `/workforce/workflows/${scenario.workflowId}/test-runs`, {
            method: "POST",
            data: { input: fixtureInput },
        });

        await login(page, credentials);
        await page.goto("/approvals");
        const rejectButton = page.getByRole("button", { name: "Reject" }).first();
        await expect(rejectButton).toBeVisible({ timeout: 30_000 });
        await page.getByLabel("Decision note").fill("Playwright rejection — unsafe write");
        await rejectButton.click();
        await expect(page.getByText(/Approval decision saved/i)).toBeVisible({ timeout: 30_000 });
    });

    test("edit email draft creates replacement approval", async ({ page, request }) => {
        const credentials = readCredentials();
        await apiSignIn(request, credentials.email, credentials.password);
        seedFixture("email-approval", credentials.userId);

        await login(page, credentials);
        await page.goto("/approvals");

        const editButton = page.getByRole("button", { name: "Edit" }).first();
        await expect(editButton).toBeVisible({ timeout: 30_000 });
        await editButton.click();
        await page.getByLabel(/Body|body/i).first().fill("Edited by Playwright E2E");
        await page.getByRole("button", { name: "Save revised draft" }).click();
        await expect(page.getByText(/updated|exact version/i)).toBeVisible({ timeout: 30_000 });
    });
});
