import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { resolve, extname, sep } from "node:path";
import { createServer as createViteServer } from "vite";
import { attachSensors } from "./sensors";
const production = process.argv.includes("--production");
const root = resolve("dist");
const vite = production
  ? null
  : await createViteServer({
      server: { middlewareMode: true },
      appType: "spa",
    });
const types: Record<string, string> = {
  ".html": "text/html",
  ".js": "text/javascript",
  ".css": "text/css",
  ".glb": "model/gltf-binary",
  ".json": "application/json",
  ".png": "image/png",
};
const server = createServer(async (req, res) => {
  if (vite) {
    vite.middlewares(req, res);
    return;
  }
  try {
    const path = resolve(
      root,
      "." +
        decodeURIComponent(
          new URL(req.url ?? "/", "http://localhost").pathname,
        ),
    );
    if (path !== root && !path.startsWith(root + sep)) {
      res.writeHead(403).end();
      return;
    }
    const target = path === root ? resolve(root, "index.html") : path;
    const body = await readFile(target);
    res.setHeader(
      "Content-Type",
      types[extname(target)] ?? "application/octet-stream",
    );
    res.end(body);
  } catch {
    res.writeHead(404).end("File not found");
  }
});
const stopSensors = attachSensors(server);
const port = Number(process.env.PORT ?? 5173);
server.listen(port, process.env.HOST ?? "127.0.0.1", () =>
  console.log(
    `Vessel viewer http://127.0.0.1:${port} (PID ${process.pid}, started ${new Date().toISOString()}, stop: kill -TERM ${process.pid})`,
  ),
);
let stopping = false;
async function shutdown() {
  if (stopping) return;
  stopping = true;
  await stopSensors();
  await vite?.close();
  server.close();
  server.closeAllConnections();
}
process.on("SIGTERM", shutdown);
process.on("SIGINT", shutdown);
