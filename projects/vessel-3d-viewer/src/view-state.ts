import type { Group, PerspectiveCamera } from "three";
/** WebXR changes the user's camera projection; restore it after XR manager cleanup. */
export function restoreDesktopLayout(
  vessel: Group,
  camera: PerspectiveCamera,
  width: number,
  height: number,
) {
  vessel.scale.setScalar(1);
  vessel.position.set(0, 0, 0);
  camera.fov = 43;
  camera.aspect = width / height;
  camera.near = 0.01;
  camera.far = 200;
  camera.updateProjectionMatrix();
}
