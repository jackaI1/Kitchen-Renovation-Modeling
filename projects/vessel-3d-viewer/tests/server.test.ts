import { it, expect } from "vitest";
import { WebSocket } from "ws";
import { createSensorServer } from "../server/sensors";
import { parseFrame } from "../src/telemetry";
it("streams real WebSocket frames, changes scenario per client and closes cleanly", async () => {
  const { server, close } = createSensorServer({ port: 0, interval: 30 });
  await new Promise<void>((r) => server.once("listening", r));
  const address = server.address() as { port: number };
  const ws = new WebSocket(`ws://127.0.0.1:${address.port}/sensors`);
  try {
    const first = await new Promise<any>((r) =>
      ws.once("message", (d) => r(JSON.parse(d.toString()))),
    );
    expect(parseFrame(first)).not.toBeNull();
    ws.send(JSON.stringify({ scenario: "flood" }));
    const flood = await new Promise<any>((resolve, reject) => {
      const timer = setTimeout(() => reject(Error("no flood frame")), 2000);
      ws.on("message", (d) => {
        const f = JSON.parse(d.toString());
        if (f.scenario === "flood") {
          clearTimeout(timer);
          resolve(f);
        }
      });
    });
    expect(flood.readings[0].level).toBeGreaterThanOrEqual(90);
  } finally {
    ws.close();
    await close();
  }
  expect(server.listening).toBe(false);
});
