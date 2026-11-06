import { readFile } from "node:fs/promises";
// The Khronos validator checks glTF accessors, buffers, geometry and references.
// @ts-expect-error The upstream validator has no TypeScript declarations.
import validator from "gltf-validator";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { validateModel } from "../src/model";
const bytes = await readFile(process.argv[2] ?? "public/models/vessel.glb");
if (bytes.length > 2_000_000) throw Error("GLB exceeds 2 MB budget");
const report = await validator.validateBytes(new Uint8Array(bytes), {
  maxIssues: 30,
});
if (report.issues.numErrors) throw Error(JSON.stringify(report.issues));
const buffer = bytes.buffer.slice(
  bytes.byteOffset,
  bytes.byteOffset + bytes.byteLength,
);
const gltf = await new GLTFLoader().parseAsync(buffer, "");
const meshes = validateModel(gltf.scene);
console.log(
  JSON.stringify({
    bytes: bytes.length,
    meshes: [...meshes.keys()],
    errors: report.issues.numErrors,
    warnings: report.issues.numWarnings,
  }),
);
