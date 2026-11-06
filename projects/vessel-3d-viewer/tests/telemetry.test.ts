import { describe, it, expect } from "vitest";
import { PARTS, parseFrame, acceptFrame, appearance } from "../src/telemetry";
import { simulate } from "../server/simulation";
const now = 1700000000000;
describe("sensor safety and mapping", () => {
  it("maps every simulated reading to a named compartment", () => {
    const f = simulate(0, now, "normal");
    expect(parseFrame(f, now)).toEqual(f);
    expect(f.readings.map((r) => r.part)).toEqual(PARTS.map((p) => p.id));
  });
  it.each([
    null,
    {},
    "bad",
    { version: 1, sequence: 0, timestamp: now, readings: [] },
  ])("rejects incomplete packets %j", (value) =>
    expect(parseFrame(value, now)).toBeNull(),
  );
  it.each([
    "unknown",
    "duplicate",
    "nan",
    "range",
    "future",
    "old",
    "sequence",
  ])("rejects %s data", (kind) => {
    const f = simulate(1, now, "normal");
    if (kind === "unknown") f.readings[0].part = "wrong";
    if (kind === "duplicate") f.readings[1].part = f.readings[0].part;
    if (kind === "nan") f.readings[0].temperature = NaN;
    if (kind === "range") f.readings[0].level = 101;
    if (kind === "future") f.timestamp += 60000;
    if (kind === "old") f.timestamp -= 60000;
    if (kind === "sequence") f.sequence = -1;
    expect(parseFrame(f, now)).toBeNull();
  });
  it("ignores out of order frames but accepts a restarted connection", () => {
    const f = simulate(3, now, "normal");
    expect(acceptFrame(f, 3)).toBe(false);
    expect(acceptFrame(f, 4)).toBe(false);
    expect(acceptFrame(f, -1)).toBe(true);
  });
  it("uses exact alarm thresholds for each metric", () => {
    expect(appearance(90, "level", false).status).toBe("Alarm");
    expect(appearance(75, "level", false).status).toBe("Watch");
    expect(appearance(74, "level", false).status).toBe("Normal");
    expect(appearance(65, "temperature", false).status).toBe("Alarm");
    expect(appearance(50, "temperature", false).status).toBe("Watch");
  });
  it("never shows stale readings as healthy", () =>
    expect(appearance(20, "temperature", true).status).toBe("Stale"));
  it("creates repeatable flood and heat scenarios inside physical bounds", () => {
    expect(simulate(1, now, "flood").readings[0].level).toBeGreaterThanOrEqual(
      90,
    );
    expect(
      simulate(1, now, "heat").readings[3].temperature,
    ).toBeGreaterThanOrEqual(65);
    for (let i = 0; i < 100; i++)
      expect(parseFrame(simulate(i, now, "normal"), now)).not.toBeNull();
  });
});
