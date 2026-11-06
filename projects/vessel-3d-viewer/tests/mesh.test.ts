import { it, expect } from "vitest";
import {
  Group,
  Mesh,
  BoxGeometry,
  MeshStandardMaterial,
  BufferGeometry,
  Float32BufferAttribute,
} from "three";
import { validateModel } from "../src/model";
import { PARTS } from "../src/telemetry";
function model() {
  const root = new Group();
  for (const id of ["hull", ...PARTS.map((p) => p.id)]) {
    const mesh = new Mesh(new BoxGeometry(), new MeshStandardMaterial());
    mesh.name = id;
    root.add(mesh);
  }
  return root;
}
it("indexes exact named meshes", () =>
  expect(validateModel(model()).size).toBe(5));
it("rejects a missing compartment", () => {
  const root = model();
  root.remove(root.children[1]);
  expect(() => validateModel(root)).toThrow(/missing/i);
});
it("rejects duplicate names", () => {
  const root = model();
  root.children[2].name = root.children[1].name;
  expect(() => validateModel(root)).toThrow(/duplicate/i);
});
it("rejects non-finite vertices", () => {
  const root = model();
  (root.children[0] as Mesh).geometry.setAttribute(
    "position",
    new Float32BufferAttribute([NaN, 0, 0, 1, 0, 0, 0, 1, 0], 3),
  );
  expect(() => validateModel(root)).toThrow(/finite/i);
});
it("rejects empty geometry", () => {
  const root = model();
  (root.children[0] as Mesh).geometry = new BufferGeometry();
  expect(() => validateModel(root)).toThrow(/geometry/i);
});
it("rejects empty indexed geometry", () => {
  const root = model();
  (root.children[0] as Mesh).geometry.setIndex([]);
  expect(() => validateModel(root)).toThrow(/geometry/i);
});
