/* eslint-disable @next/next/no-img-element -- Product Hunt's live badge is a remote SVG; next/image would rasterise it. */
import { site } from "@/lib/site";

/** Product Hunt's official "Featured" badge. Renders nothing until the listing URL and post id are set. */
export function ProductHuntBadge({ className }: { className?: string }) {
  const { url, postId } = site.productHunt;
  if (!url || !postId) return null;
  return (
    <a href={url} className={className} rel="noopener" target="_blank">
      <img
        src={`https://api.producthunt.com/widgets/embed-image/v1/featured.svg?post_id=${encodeURIComponent(postId)}&theme=light`}
        alt="Linguini on Product Hunt"
        width={250}
        height={54}
        loading="lazy"
      />
    </a>
  );
}
