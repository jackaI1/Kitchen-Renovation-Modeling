import { it, expect } from "vitest";
import { Group, PerspectiveCamera } from "three";
import { restoreDesktopLayout } from "../src/view-state";
it("restores desktop projection after a headset changes the camera", () => {
  const vessel = new Group();
  vessel.scale.setScalar(0.18);
  vessel.position.set(0, 0.9, -1.8);
  const camera = new PerspectiveCamera(95, 1, 0.01, 200);
  restoreDesktopLayout(vessel, camera, 800, 400);
  const expected = new PerspectiveCamera(43, 2, 0.01, 200);
  expect(camera.fov).toBe(43);
  expect(camera.aspect).toBe(2);
  expect(camera.projectionMatrix.elements).toEqual(
    expected.projectionMatrix.elements,
  );
  expect(vessel.scale.toArray()).toEqual([1, 1, 1]);
  expect(vessel.position.toArray()).toEqual([0, 0, 0]);
});
