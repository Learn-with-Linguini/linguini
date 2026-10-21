import { useOutletContext } from "react-router-dom";
import type { Scene } from "../data/types";

// Practice screens mount only after SceneRoute has loaded a valid scene.
export function useScene(): Scene {
  return useOutletContext<Scene>();
}
