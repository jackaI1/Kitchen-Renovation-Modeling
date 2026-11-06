export const PARTS = [
  { id: "tank_port", label: "Port ballast" },
  { id: "tank_starboard", label: "Starboard ballast" },
  { id: "tank_freshwater", label: "Fresh water" },
  { id: "engine_room", label: "Engine room" },
] as const;
export type Metric = "level" | "temperature";
export type Scenario = "normal" | "flood" | "heat";
export interface Reading {
  part: string;
  level: number;
  temperature: number;
}
export interface Frame {
  version: 1;
  sequence: number;
  timestamp: number;
  scenario: Scenario;
  readings: Reading[];
}
export const STALE_MS = 5000;
export function parseFrame(value: unknown, now = Date.now()): Frame | null {
  if (!value || typeof value !== "object") return null;
  const f = value as Frame;
  if (
    f.version !== 1 ||
    !Number.isSafeInteger(f.sequence) ||
    f.sequence < 0 ||
    !Number.isFinite(f.timestamp) ||
    f.timestamp > now + 2000 ||
    now - f.timestamp > STALE_MS ||
    !["normal", "flood", "heat"].includes(f.scenario) ||
    !Array.isArray(f.readings) ||
    f.readings.length !== PARTS.length
  )
    return null;
  const seen = new Set<string>();
  for (const r of f.readings) {
    if (
      !r ||
      !PARTS.some((p) => p.id === r.part) ||
      seen.has(r.part) ||
      !Number.isFinite(r.level) ||
      r.level < 0 ||
      r.level > 100 ||
      !Number.isFinite(r.temperature) ||
      r.temperature < -20 ||
      r.temperature > 120
    )
      return null;
    seen.add(r.part);
  }
  return f;
}
export function acceptFrame(frame: Frame, previous: number) {
  return frame.sequence > previous;
}
export function appearance(value: number, metric: Metric, stale: boolean) {
  if (stale) return { color: "#737f89", status: "Stale" };
  const [watch, alarm] = metric === "level" ? [75, 90] : [50, 65];
  return value >= alarm
    ? { color: "#ba342e", status: "Alarm" }
    : value >= watch
      ? { color: "#a26300", status: "Watch" }
      : { color: "#247da0", status: "Normal" };
}
