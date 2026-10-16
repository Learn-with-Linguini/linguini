import type { CSSProperties, ImgHTMLAttributes } from "react";

export type ImageProps = Omit<ImgHTMLAttributes<HTMLImageElement>, "fetchPriority" | "src"> & {
  src: string;
  fill?: boolean;
  priority?: boolean;
  sizes?: string;
};

export default function Image({ fill, loading, priority = false, sizes, style, ...props }: ImageProps) {
  const fillStyle: CSSProperties | undefined = fill
    ? { position: "absolute", inset: 0, width: "100%", height: "100%" }
    : undefined;

  return (
    <img
      {...props}
      sizes={sizes}
      loading={priority ? "eager" : loading ?? "lazy"}
      fetchPriority={priority ? "high" : undefined}
      style={fill ? { ...style, ...fillStyle } : style}
    />
  );
}
