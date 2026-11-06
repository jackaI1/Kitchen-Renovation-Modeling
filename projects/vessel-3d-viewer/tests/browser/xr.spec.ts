import { test, expect } from "@playwright/test";

// Close each owned test page on success and failure before the next test.
test.afterEach(async ({ page }) => {
  if (!page.isClosed()) await page.close();
});
import { buildSync } from "esbuild";
const runtime = buildSync({
  stdin: {
    contents:
      "import {XRDevice,metaQuest3} from 'iwer'; const device=new XRDevice(metaQuest3); device.installRuntime({forceInstall:true}); device.position.set(0,1.6,0); const request=navigator.xr.requestSession.bind(navigator.xr); navigator.xr.requestSession=async(...args)=>{const session=await request(...args); window.testSession=session; return session;};",
    resolveDir: process.cwd(),
  },
  bundle: true,
  format: "iife",
  write: false,
}).outputFiles[0].text;
test("enters and exits an emulated immersive session with live telemetry", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.addInitScript({ content: runtime });
  await page.goto("/");
  await expect(page.locator("#model-status")).toHaveText(
    "5 named parts loaded",
  );
  await page.selectOption("#scenario", "flood");
  await expect(page.locator("#xr")).toBeEnabled();
  await page.locator("#xr").click();
  await expect(page.locator("#xr")).toHaveText("Exit immersive view");
  const readingTime = await page.locator("#updated").textContent();
  await expect(page.locator("#updated")).not.toHaveText(readingTime!, { timeout: 5000 });
  await expect(page.locator('[data-part="tank_port"]')).toContainText("Alarm");
  await page.evaluate(async () => {
    await (window as unknown as { testSession: XRSession }).testSession.end();
  });
  await expect(page.locator("#xr-status")).toContainText("Orbit view restored");
  await page.locator("#xr").click();
  await expect(page.locator("#xr")).toHaveText("Exit immersive view");
  await page.evaluate(async () => {
    await (window as unknown as { testSession: XRSession }).testSession.end();
  });
  await expect(page.locator("#xr-status")).toContainText("Orbit view restored");
  expect(errors).toEqual([]);
});
