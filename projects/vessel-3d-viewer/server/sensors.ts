import { createServer, type Server } from "node:http";
import { WebSocketServer, WebSocket } from "ws";
import { simulate } from "./simulation";
import type { Scenario } from "../src/telemetry";
export function attachSensors(server: Server, interval = 1000) {
  const wss = new WebSocketServer({
    server,
    path: "/sensors",
    maxPayload: 1024,
  });
  wss.on("connection", (socket) => {
    let sequence = 0;
    let scenario: Scenario = "normal";
    const send = () => {
      if (socket.readyState === WebSocket.OPEN && socket.bufferedAmount < 65536)
        socket.send(JSON.stringify(simulate(sequence++, Date.now(), scenario)));
    };
    send();
    const timer = setInterval(send, interval);
    socket.on("message", (data) => {
      try {
        const value = JSON.parse(data.toString());
        if (["normal", "flood", "heat"].includes(value.scenario)) {
          scenario = value.scenario;
          send();
        }
      } catch {
        /* Ignore invalid control packets. */
      }
    });
    socket.on("close", () => clearInterval(timer));
    socket.on("error", () => socket.close());
  });
  return async () => {
    for (const client of wss.clients) client.terminate();
    await new Promise<void>((resolve) => wss.close(() => resolve()));
  };
}
export function createSensorServer({ port = 8787, interval = 1000 } = {}) {
  const server = createServer();
  const stop = attachSensors(server, interval);
  server.listen(port, "127.0.0.1");
  return {
    server,
    close: async () => {
      await stop();
      await new Promise<void>((r) => server.close(() => r()));
    },
  };
}
