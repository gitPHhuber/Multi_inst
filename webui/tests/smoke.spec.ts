import { test, expect } from "@playwright/test";

const DEV_SERVER = "http://127.0.0.1:5173";

test("dashboard renders", async ({ page }) => {
  await page.goto(`${DEV_SERVER}/?sim=1`);
  const title = page.locator("text=Multi Inst Dashboard");
  await expect(title).toBeVisible();
});
