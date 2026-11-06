import { Mesh, Object3D } from "three";
import { PARTS } from "./telemetry";
export function validateModel(root: Object3D): Map<string, Mesh> {
  const meshes = new Map<string, Mesh>();
  let triangles = 0;
  root.traverse((obj) => {
    if (!(obj instanceof Mesh)) return;
    if (meshes.has(obj.name)) throw Error(`Duplicate mesh: ${obj.name}`);
    const positions = obj.geometry.getAttribute("position");
    if (!positions || positions.count < 3)
      throw Error(`Empty geometry: ${obj.name}`);
    for (const value of positions.array)
      if (!Number.isFinite(value))
        throw Error(`Non-finite vertex: ${obj.name}`);
    const count = obj.geometry.index?.count ?? positions.count;
    if (count < 3 || count % 3)
      throw Error(`Non-triangle geometry: ${obj.name}`);
    triangles += count / 3;
    meshes.set(obj.name, obj);
  });
  for (const name of ["hull", ...PARTS.map((p) => p.id)])
    if (!meshes.has(name)) throw Error(`Missing mesh: ${name}`);
  if (triangles > 20000) throw Error("Model exceeds 20,000 triangle budget");
  return meshes;
}
