import Image, { type ImageProps } from "next/image";

/** Intrinsic sizes of the public images the launch post uses. */
const DIMS: Record<string, [number, number]> = {
  "/brand/mascot-180.png": [180, 180],
  "/pasta/farfalle.png": [360, 281],
  "/pasta/fusilli.png": [276, 360],
  "/pasta/penne.png": [360, 341],
  "/blog/launch/01-your-world.jpg": [1270, 760],
  "/blog/launch/02-find-your-words.jpg": [1270, 760],
  "/blog/launch/03-play-and-build.jpg": [1270, 760],
  "/blog/launch/04-keep-the-day.jpg": [1270, 760],
  "/blog/launch/product-hunt-icon-240.png": [240, 240],
  "/blog/launch/explainer-poster.jpg": [1920, 1080],
  "/blog/launch/social-square.jpg": [1080, 1080],
  "/blog/launch/countdown-1080x1080.jpg": [1080, 1080],
  "/blog/launch/ig-post-1080x1350.jpg": [1080, 1350],
  "/blog/launch/ig-story-1080x1920.jpg": [1080, 1920],
  "/blog/launch/ig-story-countdown-1080x1920.jpg": [1080, 1920],
  "/blog/launch/launch-card-1200x630.jpg": [1200, 630],
  "/blog/launch/linkedin-1584x396.jpg": [1584, 396],
  "/blog/launch/x-header-1500x500.jpg": [1500, 500],
};

/** Width over height of a known public image. */
export function ratio(src: string) {
  const [width, height] = DIMS[src] ?? [1200, 800];
  return width / height;
}

/** next/image for a known public file, so callers only pass the path. */
export function Img({ src, alt, ...rest }: Omit<ImageProps, "src" | "width" | "height"> & { src: string }) {
  const [width, height] = DIMS[src] ?? [1200, 800];
  return <Image src={src} alt={alt} width={width} height={height} {...rest} />;
}
