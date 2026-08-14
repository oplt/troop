import type { Page } from "@playwright/test";
import type { E2ECredentials } from "./credentials";

export async function login(page: Page, credentials: E2ECredentials) {
    await page.goto("/");
    await page.getByLabel("Email").fill(credentials.email);
    await page.getByLabel("Password", { exact: true }).fill(credentials.password);
    await page.getByRole("button", { name: "Sign in" }).click();
    await page.waitForURL("**/dashboard", { timeout: 30_000 });
}
