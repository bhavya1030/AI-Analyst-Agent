import { test, expect } from "@playwright/test";

test("frontend communicates with backend", async ({ page }) => {
  await page.goto("http://localhost:3000");
  await page.fill("textarea", "find dataset about gdp");

  const askResponse = page.waitForResponse((response) =>
    response.url().includes("/v1/ask") && response.request().method() === "GET"
  );

  await page.click("button[type='submit']");

  const response = await askResponse;
  expect(response.status()).toBe(200);

  const data = await response.json();
  expect(data.answer).toBeDefined();
});
