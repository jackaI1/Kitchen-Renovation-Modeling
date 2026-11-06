import { test, expect } from "@playwright/test";

// Close each owned test page on success and failure before the next test.
test.afterEach(async ({ page }) => {
  if (!page.isClosed()) await page.close();
});
test("loads the exported model, live readings and inspection controls", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await expect(page.locator("#model-status")).toHaveText(
    "5 named parts loaded",
  );
  await expect(page.locator("#connection")).toContainText("Live");
  await expect(page.locator("#readings button")).toHaveCount(4);
  await page.selectOption("#scenario", "flood");
  await expect(page.locator('[data-part="tank_port"]')).toContainText("Alarm");
  await page.selectOption("#metric", "temperature");
  await page.selectOption("#scenario", "heat");
  await expect(page.locator('[data-part="engine_room"]')).toContainText(
    "78 °C",
  );
  await page.locator('[data-part="engine_room"]').click();
  await expect(page.locator("#selection")).toContainText("Engine room");
  await page.getByRole("button", { name: "Reset view" }).click();
  await expect(page.locator("#xr-status")).not.toBeEmpty();
  await page.screenshot({ path: "test-results/desktop.png", fullPage: true });
  expect(errors).toEqual([]);
});
test("fits a phone and marks disconnected readings stale", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(page.locator("#connection")).toContainText("Live");
  await expect(page.locator("#model-status")).toContainText("5 named");
  await page.screenshot({ path: "test-results/mobile.png", fullPage: true });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.context().setOffline(true);
  await expect(page.locator("#connection")).toContainText(
    /Stale|Reconnecting/,
    { timeout: 12000 },
  );
  await expect(page.locator('[data-part="tank_port"]')).toContainText("Stale", {
    timeout: 12000,
  });
  await page.context().setOffline(false);
  await expect(page.locator("#connection")).toContainText("Live", {
    timeout: 15000,
  });
});
test("resumes live updates after a persisted page lifecycle", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page.locator("#connection")).toContainText("Live");
  const before = await page.locator("#updated").textContent();
  await page.evaluate(() => {
    window.dispatchEvent(
      new PageTransitionEvent("pagehide", { persisted: true }),
    );
    window.dispatchEvent(
      new PageTransitionEvent("pageshow", { persisted: true }),
    );
  });
  await expect(page.locator("#updated")).not.toHaveText(before!, {
    timeout: 6000,
  });
  await expect(page.locator("#connection")).toContainText("Live");
});
