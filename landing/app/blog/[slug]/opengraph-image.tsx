import { ImageResponse } from "next/og";
import { getPost, posts } from "@/data/posts";
import {
  OG_SIZE,
  Pasta,
  Print,
  Tape,
  Wordmark,
  cleanText,
  loadImage,
  loadOgFonts,
  loadPasta,
  loadWordmark,
  ogColors,
  ogFont,
} from "@/lib/og";
import { getPhoto, photos } from "@/lib/photos";
import { site } from "@/lib/site";

export const runtime = "nodejs";
export const alt = "A Linguini blog post: the title beside a real photo printed and taped to the page.";
export const size = OG_SIZE;
export const contentType = "image/png";

/** Posts with a video cover get a fixed photo so each card stays recognisable. */
const PHOTO_FOR_SLUG: Record<string, string> = {
  "launch-week": "paris-rooftops",
  "linguini-business-model": "cafe-interior",
};

export function generateStaticParams() {
  return posts.map(post => ({ slug: post.slug }));
}

export default async function PostImage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const post = getPost(slug) ?? posts[0]!;
  const stem = post.cover.kind === "photo" ? post.cover.scene : PHOTO_FOR_SLUG[post.slug];
  const photo = (stem && getPhoto(stem)) || photos[posts.indexOf(post) % photos.length]!;

  const [fonts, wordmark, photoSrc, macaroni] = await Promise.all([
    loadOgFonts(),
    loadWordmark(),
    loadImage(`public/photos/${photo.file}`),
    loadPasta("macaroni"),
  ]);

  const titleLength = Array.from(post.title).length;
  const titleSize = titleLength <= 28 ? 76 : titleLength <= 44 ? 64 : 54;

  return new ImageResponse(
    (
      <div
        style={{
          display: "flex",
          position: "relative",
          width: "100%",
          height: "100%",
          background: ogColors.butter,
          fontFamily: ogFont.ui,
          color: ogColors.ink,
          overflow: "hidden",
        }}
      >
        <div
          style={{
            display: "flex",
            position: "absolute",
            left: 700,
            top: -60,
            width: 620,
            height: 760,
            background: ogColors.cream,
            borderRadius: 64,
            transform: "rotate(5deg)",
          }}
        />
        <Print src={photoSrc} width={420} height={440} rotate={4} border={16} style={{ left: 722, top: 96 }} />
        <Tape width={128} rotate={-6} style={{ left: 866, top: 78 }} />
        <Pasta src={macaroni} shape="macaroni" width={104} rotate={-18} style={{ left: 1060, top: 486 }} />

        <div
          style={{
            display: "flex",
            flexDirection: "column",
            position: "absolute",
            left: 72,
            top: 64,
            width: 600,
            height: 502,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 18 }}>
            <Wordmark src={wordmark} width={170} />
            <div
              style={{
                display: "flex",
                padding: "6px 16px",
                borderRadius: 999,
                background: ogColors.teal,
                color: ogColors.paper,
                fontSize: 22,
              }}
            >
              {`Blog · ${post.category}`}
            </div>
          </div>

          <div style={{ display: "flex", flexDirection: "column", justifyContent: "center", flexGrow: 1 }}>
            <div
              style={{
                display: "flex",
                fontFamily: ogFont.display,
                fontWeight: 800,
                fontSize: titleSize,
                lineHeight: 1,
                letterSpacing: -1,
              }}
            >
              {post.title}
            </div>
            <div style={{ display: "flex", marginTop: 24, fontSize: 26, lineHeight: 1.35, color: ogColors.muted }}>
              {cleanText(post.summary, 120)}
            </div>
          </div>

          <div style={{ display: "flex", fontSize: 22, color: ogColors.tealDark }}>
            {`${post.readMinutes} min read · ${site.url.replace(/^https?:\/\//, "")}`}
          </div>
        </div>
      </div>
    ),
    { ...OG_SIZE, fonts },
  );
}
