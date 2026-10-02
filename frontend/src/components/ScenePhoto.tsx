import type { KeyboardEvent, MouseEvent } from "react";
import { SceneVisual } from "./SceneVisual";
import type { LanguageItem, Scene } from "../data/types";

type Props = {
  scene: Scene;
  items?: LanguageItem[];
  activeItemId?: string | null;
  onMarkerClick?: (item: LanguageItem) => void;
  onLocationSelect?: (position: { x: number; y: number }) => void;
  locationLabel?: string;
  lazy?: boolean;
};

export function ScenePhoto({
  scene,
  items,
  activeItemId,
  onMarkerClick,
  onLocationSelect,
  locationLabel,
  lazy,
}: Props) {
  const markers = items ?? scene.items;

  const selectLocation = (event: MouseEvent<HTMLDivElement>) => {
    if (!onLocationSelect || event.currentTarget.querySelector(".scene-image--error")) return;

    const bounds = event.currentTarget.getBoundingClientRect();
    if (!bounds.width || !bounds.height) return;
    onLocationSelect({
      x: Math.max(0, Math.min(100, ((event.clientX - bounds.left) / bounds.width) * 100)),
      y: Math.max(0, Math.min(100, ((event.clientY - bounds.top) / bounds.height) * 100)),
    });
  };

  const selectCenterWithKeyboard = (event: KeyboardEvent<HTMLDivElement>) => {
    if (!onLocationSelect || (event.key !== "Enter" && event.key !== " ")) return;
    event.preventDefault();
    if (event.currentTarget.querySelector(".scene-image--error")) return;
    onLocationSelect({ x: 50, y: 50 });
  };

  return (
    <div
      className={`scene${onLocationSelect ? " scene--location-selectable" : ""}`}
      onClick={selectLocation}
      onKeyDown={selectCenterWithKeyboard}
      role={onLocationSelect ? "button" : undefined}
      tabIndex={onLocationSelect ? 0 : undefined}
      aria-label={onLocationSelect ? locationLabel ?? "Choose a location in the scene" : undefined}
    >
      <SceneVisual scene={scene} className="scene__art" lazy={lazy} />
      {markers.map((item) => {
        const active = item.id === activeItemId;
        const custom = item.id.startsWith("custom-");
        const className = [
          "scene__marker",
          custom ? "scene__marker--custom" : "",
          active ? "scene__marker--active" : "",
          item.y < 12 ? "scene__marker--below" : "",
          item.x > 86 ? "scene__marker--left" : "",
        ]
          .filter(Boolean)
          .join(" ");
        const style = { left: `${item.x}%`, top: `${item.y}%` };
        // Placement mode has one keyboard target, without nested marker buttons.
        return onMarkerClick && !onLocationSelect ? (
          <button
            key={item.id}
            type="button"
            className={className}
            style={style}
            onClick={() => onMarkerClick(item)}
            aria-label={`Marker ${item.marker}: ${item.word}`}
            aria-pressed={active}
          >
            <span className="scene__marker-label">{item.marker}</span>
          </button>
        ) : (
          <span key={item.id} className={className} style={style} aria-hidden="true">
            <span className="scene__marker-label">{item.marker}</span>
          </span>
        );
      })}
    </div>
  );
}
