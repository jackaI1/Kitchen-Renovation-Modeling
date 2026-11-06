import { PARTS, type Frame, type Scenario } from "../src/telemetry";
export function simulate(
  sequence: number,
  timestamp = Date.now(),
  scenario: Scenario = "normal",
): Frame {
  return {
    version: 1,
    sequence,
    timestamp,
    scenario,
    readings: PARTS.map((p, i) => ({
      part: p.id,
      level:
        scenario === "flood" && i === 0
          ? 96
          : Math.round(42 + 18 * Math.sin(sequence / 14 + i)),
      temperature:
        scenario === "heat" && i === 3
          ? 78
          : Math.round((i === 3 ? 43 : 23) + 5 * Math.sin(sequence / 20 + i)),
    })),
  };
}
