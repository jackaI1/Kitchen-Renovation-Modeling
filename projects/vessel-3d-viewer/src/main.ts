import "./style.css";
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import {
  PARTS,
  STALE_MS,
  parseFrame,
  acceptFrame,
  appearance,
  type Metric,
  type Frame,
  type Scenario,
} from "./telemetry";
import { validateModel } from "./model";
import { restoreDesktopLayout } from "./view-state";
const el = <T extends HTMLElement>(id: string) =>
  document.getElementById(id) as T;
const viewport = el("viewport");
const status = el("connection");
const metricSelect = el<HTMLSelectElement>("metric"),
  scenarioSelect = el<HTMLSelectElement>("scenario");
let metric: Metric = "level",
  frame: Frame | null = null,
  sequence = -1,
  connected = false,
  selected = "";
let socket: WebSocket | undefined,
  retry: ReturnType<typeof setTimeout> | undefined,
  disposed = false;
const rows = new Map<string, HTMLButtonElement>();
for (const part of PARTS) {
  const row = document.createElement("button");
  row.dataset.part = part.id;
  row.setAttribute("aria-pressed", "false");
  row.addEventListener("click", () => selectPart(part.id));
  el("readings").append(row);
  rows.set(part.id, row);
}
let meshes = new Map<string, THREE.Mesh>();
const labels = new Map<
  string,
  {
    sprite: THREE.Sprite;
    canvas: HTMLCanvasElement;
    texture: THREE.CanvasTexture;
    text: string;
  }
>();
let renderer: THREE.WebGLRenderer;
try {
  renderer = new THREE.WebGLRenderer({ antialias: true });
} catch {
  el("loading").textContent =
    "3D rendering is unavailable. Enable WebGL in your browser and reload.";
  throw Error("WebGL unavailable");
}
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.xr.enabled = true;
renderer.setClearColor("#e7eff3");
viewport.append(renderer.domElement);
const scene = new THREE.Scene();
scene.add(new THREE.HemisphereLight(0xffffff, 0x566c7c, 2.5));
const sun = new THREE.DirectionalLight(0xffffff, 2.5);
sun.position.set(2, 8, 5);
scene.add(sun);
const camera = new THREE.PerspectiveCamera(43, 1, 0.01, 200);
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.minDistance = 5;
controls.maxDistance = 30;
controls.maxPolarAngle = Math.PI * 0.47;
const vessel = new THREE.Group();
scene.add(vessel);
function reset() {
  controls.target.set(0, 1, 0);
  const direction = new THREE.Vector3(1, 1.15, 1.35).normalize();
  let distance = 22;
  // Fit the known hull and label envelope to the current viewport, not just desktop.
  for (let i = 0; i < 4; i++) {
    camera.position.copy(controls.target).addScaledVector(direction, distance);
    camera.lookAt(controls.target);
    camera.updateMatrixWorld();
    let extent = 0;
    for (const x of [-6, 6])
      for (const y of [0, 3.2])
        for (const z of [-1.8, 1.8]) {
          const point = new THREE.Vector3(x, y, z).project(camera);
          extent = Math.max(extent, Math.abs(point.x), Math.abs(point.y));
        }
    distance = Math.max(5, (distance * extent) / 0.86);
  }
  camera.position.copy(controls.target).addScaledVector(direction, distance);
  controls.update();
}
reset();
el("reset").addEventListener("click", reset);
const resize = new ResizeObserver(() => {
  const { width, height } = viewport.getBoundingClientRect();
  camera.aspect = width / height;
  camera.updateProjectionMatrix();
  renderer.setSize(width, height);
  if (!renderer.xr.isPresenting) reset();
});
resize.observe(viewport);
function selectPart(id: string) {
  selected = id;
  const p = PARTS.find((p) => p.id === id);
  el("selection").textContent = p
    ? `Inspecting ${p.label}.`
    : "Select a compartment.";
  for (const [key, row] of rows)
    row.setAttribute("aria-pressed", String(key === id));
}
const raycaster = new THREE.Raycaster();
let downX = 0,
  downY = 0;
renderer.domElement.addEventListener("pointerdown", (e) => {
  downX = e.clientX;
  downY = e.clientY;
});
renderer.domElement.addEventListener("pointerup", (e) => {
  if (Math.hypot(e.clientX - downX, e.clientY - downY) > 5) return;
  const rect = renderer.domElement.getBoundingClientRect();
  raycaster.setFromCamera(
    new THREE.Vector2(
      ((e.clientX - rect.left) / rect.width) * 2 - 1,
      (-(e.clientY - rect.top) / rect.height) * 2 + 1,
    ),
    camera,
  );
  pick();
});
function pick() {
  const hit = raycaster.intersectObjects(
    [...meshes.values()].filter((m) => m.name !== "hull"),
    false,
  )[0];
  if (hit) selectPart(hit.object.name);
}
for (let i = 0; i < 2; i++) {
  const controller = renderer.xr.getController(i);
  controller.addEventListener("select", () => {
    const rotation = new THREE.Matrix4().extractRotation(
      controller.matrixWorld,
    );
    raycaster.ray.origin.setFromMatrixPosition(controller.matrixWorld);
    raycaster.ray.direction.set(0, 0, -1).applyMatrix4(rotation);
    pick();
  });
  scene.add(controller);
}
function makeLabel(id: string, mesh: THREE.Mesh) {
  const canvas = document.createElement("canvas");
  canvas.width = 512;
  canvas.height = 128;
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  const sprite = new THREE.Sprite(
    new THREE.SpriteMaterial({
      map: texture,
      depthTest: false,
      transparent: true,
    }),
  );
  const box = new THREE.Box3().setFromObject(mesh);
  box.getCenter(sprite.position);
  sprite.position.y = box.max.y + 0.65;
  sprite.scale.set(2.9, 0.725, 1);
  sprite.renderOrder = 10;
  vessel.add(sprite);
  labels.set(id, { sprite, canvas, texture, text: "" });
}
new GLTFLoader().load(
  `${import.meta.env.BASE_URL}models/vessel.glb`,
  (gltf) => {
    try {
      meshes = validateModel(gltf.scene);
      vessel.add(gltf.scene);
      for (const [id, mesh] of meshes) {
        const material = new THREE.MeshStandardMaterial({
          color: id === "hull" ? "#809baa" : "#737f89",
          roughness: 0.6,
          metalness: 0.08,
          side: THREE.DoubleSide,
        });
        if (id === "hull") {
          material.transparent = true;
          material.opacity = 0.26;
          material.depthWrite = false;
          mesh.renderOrder = -1;
        }
        mesh.material = material;
        if (id !== "hull") makeLabel(id, mesh);
      }
      el("loading").remove();
      el("model-status").textContent = `${meshes.size} named parts loaded`;
    } catch (error) {
      el("loading").textContent =
        `Model rejected: ${(error as Error).message}. See the import guide.`;
      el("model-status").textContent = "Model validation failed";
    }
  },
  undefined,
  () => {
    el("loading").textContent =
      "Vessel model could not load. Check /models/vessel.glb and reload.";
    el("model-status").textContent = "Model load failed";
  },
);
function connect() {
  if (disposed) return;
  clearTimeout(retry);
  sequence = -1;
  const ws = new WebSocket(
    `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/sensors`,
  );
  socket = ws;
  socket.onopen = () => {
    if (socket !== ws) return;
    connected = true;
    socket?.send(JSON.stringify({ scenario: scenarioSelect.value }));
  };
  socket.onmessage = (event) => {
    if (socket !== ws) return;
    try {
      const next = parseFrame(JSON.parse(event.data));
      if (next && acceptFrame(next, sequence)) {
        frame = next;
        sequence = next.sequence;
      }
    } catch {
      /* Keep last valid frame; it expires after five seconds. */
    }
  };
  socket.onclose = () => {
    if (socket !== ws) return;
    connected = false;
    if (!disposed) retry = setTimeout(connect, 1500);
  };
  socket.onerror = () => ws.close();
}
connect();
scenarioSelect.addEventListener("change", () => {
  if (socket?.readyState === WebSocket.OPEN)
    socket.send(JSON.stringify({ scenario: scenarioSelect.value as Scenario }));
});
metricSelect.addEventListener("change", () => {
  metric = metricSelect.value as Metric;
});
let lastPaint = 0;
function paint() {
  const stale = !connected || !frame || Date.now() - frame.timestamp > STALE_MS;
  status.textContent = !connected
    ? "Reconnecting…"
    : stale
      ? "Stale readings"
      : "Live simulated readings";
  el("thresholds").textContent =
    metric === "level"
      ? "Tank level: watch at 75%, alarm at 90%."
      : "Temperature: watch at 50 °C, alarm at 65 °C.";
  el("updated").textContent = frame
    ? `Last reading ${new Date(frame.timestamp).toLocaleTimeString()}`
    : "Waiting for first reading";
  for (const part of PARTS) {
    const reading = frame?.readings.find((r) => r.part === part.id);
    const value = reading?.[metric] ?? 0;
    const style = appearance(value, metric, stale);
    const text = stale
      ? "Stale"
      : `${Math.round(value)}${metric === "level" ? "%" : " °C"}`;
    const row = rows.get(part.id)!;
    const html = `<strong>${part.label}</strong><span class="reading-values"><span>${text}</span><span class="reading-status" style="color:${style.color}">${style.status}</span></span>`;
    if (row.innerHTML !== html) row.innerHTML = html;
    const mesh = meshes.get(part.id);
    if (mesh) {
      const material = mesh.material as THREE.MeshStandardMaterial;
      material.color.set(style.color);
      material.emissive.set(part.id === selected ? "#254050" : "#000000");
    }
    const label = labels.get(part.id);
    const content = `${part.label}  ${text}  ${style.status}`;
    if (label && label.text !== content) {
      label.text = content;
      const ctx = label.canvas.getContext("2d")!;
      ctx.clearRect(0, 0, 512, 128);
      ctx.fillStyle = "#f6f9fa";
      ctx.fillRect(0, 0, 512, 128);
      ctx.fillStyle = "#18394c";
      ctx.textAlign = "center";
      ctx.font = "bold 44px sans-serif";
      ctx.fillText(part.label, 256, 46);
      ctx.fillStyle = style.color;
      ctx.font = "38px sans-serif";
      ctx.fillText(`${text} · ${style.status}`, 256, 92);
      label.texture.needsUpdate = true;
    }
  }
}
const xrButton = el<HTMLButtonElement>("xr");
const xrStatus = el("xr-status");
let session: XRSession | undefined;
async function setupXR() {
  try {
    if (
      !navigator.xr ||
      !(await navigator.xr.isSessionSupported("immersive-vr"))
    ) {
      xrStatus.textContent =
        "No compatible headset detected. Orbit view is available.";
      return;
    }
    xrButton.disabled = false;
    xrStatus.textContent =
      "Headset ready. Enter for a tabletop vessel with live labels; point and select a compartment.";
  } catch {
    xrStatus.textContent =
      "Headset access is unavailable. Use HTTPS or localhost and allow XR access.";
  }
}
void setupXR();
function restoreDesktop() {
  session = undefined;
  const rect = viewport.getBoundingClientRect();
  restoreDesktopLayout(vessel, camera, rect.width, rect.height);
  controls.enabled = true;
  reset();
  xrButton.disabled = false;
  xrButton.textContent = "Enter immersive view";
  xrStatus.textContent = "Immersive view ended. Orbit view restored.";
}
renderer.xr.addEventListener("sessionend", restoreDesktop);
xrButton.addEventListener("click", async () => {
  try {
    if (session) {
      await session.end();
      return;
    }
    xrButton.disabled = true;
    session = await navigator.xr!.requestSession("immersive-vr", {
      optionalFeatures: ["local-floor"],
    });
    controls.enabled = false;
    vessel.scale.setScalar(0.18);
    vessel.position.set(0, 0.9, -1.8);
    camera.position.set(0, 1.6, 0);
    await renderer.xr.setSession(session);
    xrButton.textContent = "Exit immersive view";
    xrButton.disabled = false;
  } catch {
    if (session)
      try {
        await session.end();
      } catch {
        /* A rejected session may already be closed. */
      }
    restoreDesktop();
    xrStatus.textContent =
      "Could not enter immersive view. Check headset permissions and try again.";
  }
});
renderer.setAnimationLoop((time) => {
  if (time - lastPaint > 200) {
    paint();
    lastPaint = time;
  }
  if (!renderer.xr.isPresenting) controls.update();
  renderer.render(scene, camera);
});
window.addEventListener("pageshow", (event) => {
  if (event.persisted) {
    disposed = false;
    connect();
  }
});
window.addEventListener("pagehide", (event) => {
  disposed = true;
  clearTimeout(retry);
  socket?.close();
  socket = undefined;
  connected = false;
  void session?.end();
  if (event.persisted) return;
  resize.disconnect();
  renderer.setAnimationLoop(null);
  controls.dispose();
  for (const { texture, sprite } of labels.values()) {
    texture.dispose();
    (sprite.material as THREE.SpriteMaterial).dispose();
  }
  scene.traverse((obj) => {
    if (obj instanceof THREE.Mesh) {
      obj.geometry.dispose();
      const materials = Array.isArray(obj.material)
        ? obj.material
        : [obj.material];
      for (const material of materials) material.dispose();
    }
  });
  renderer.dispose();
});
