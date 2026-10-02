/* eslint-disable @next/next/no-img-element -- Satori renders plain <img>, not next/image. */
import { ImageResponse } from "next/og";
import {
  OG_SIZE,
  Pasta,
  Print,
  WordTag,
  Wordmark,
  coverPoint,
  loadImage,
  loadOgFonts,
  loadPasta,
  loadWordmark,
  ogColors,
  ogFont,
  printPhotoArea,
} from "@/lib/og";
import { getPhoto, photos, type Photo } from "@/lib/photos";
import { site } from "@/lib/site";

export const runtime = "nodejs";
export const alt = site.ogImageAlt;
export const size = OG_SIZE;
export const contentType = "image/png";

const HERO_STEM = "cafe-interior";
const SUPPORTING_STEMS = ["paris-rooftops", "hillside-street"];

/** The tagged print should show a table (the café); fall back gracefully if the set changes. */
function pickPhotos(): { hero: Photo; back: Photo; side: Photo; tagAt?: { x: number; y: number } } {
  const hasTable = (p: Photo) => p.objects.some((o) => o.en.toLowerCase() === "table");
  const hero = getPhoto(HERO_STEM) ?? photos.find(hasTable) ?? photos[0]!;
  const rest = [
    ...SUPPORTING_STEMS.map((stem) => getPhoto(stem)).filter((p): p is Photo => Boolean(p)),
    ...photos,
  ].filter((p) => p.stem !== hero.stem);
  const back = rest[0] ?? hero;
  const side = rest.find((p) => p.stem !== back.stem) ?? back;
  const table = hero.objects.find((o) => o.en.toLowerCase() === "table");
  return { hero, back, side, tagAt: table ? { x: table.x, y: table.y } : undefined };
}

export default async function OpengraphImage() {
  const { hero, back, side, tagAt } = pickPhotos();
  const [fonts, wordmark, heroSrc, backSrc, sideSrc, farfalle, fusilli] = await Promise.all([
    loadOgFonts(),
    loadWordmark(),
    loadImage(`public/photos/${hero.file}`),
    loadImage(`public/photos/${back.file}`),
    loadImage(`public/photos/${side.file}`),
    loadPasta("farfalle"),
    loadPasta("fusilli"),
  ]);

  // Hero print geometry (in canvas px) and the tag anchored to the table in it.
  const HERO = { w: 424, h: 368, left: 656, top: 158, rotate: 3 };
  const area = printPhotoArea(HERO.w, HERO.h, 16);
  const pin = coverPoint(hero, area, tagAt ?? { x: 45, y: 62 });
  const tagLeft = Math.max(-36, Math.min(area.x + pin.x - 22, HERO.w - 250));
  const tagTop = Math.max(area.y + 24, Math.min(area.y + pin.y - 26, area.y + area.h - 40));

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
        {/* Warm table-top the prints are scattered on. */}
        <div
          style={{
            display: "flex",
            position: "absolute",
            left: 612,
            top: -40,
            width: 700,
            height: 720,
            background: ogColors.cream,
            borderRadius: 64,
            transform: "rotate(-4deg)",
          }}
        />

        <Pasta src={fusilli} shape="fusilli" width={92} rotate={28} style={{ left: 1098, top: 18 }} />

        <Print src={backSrc} width={300} height={262} rotate={-8} border={12} style={{ left: 640, top: 44 }} />
        <Print src={sideSrc} width={262} height={228} rotate={8} border={12} style={{ left: 930, top: 368 }} />
        <Print
          src={heroSrc}
          width={HERO.w}
          height={HERO.h}
          rotate={HERO.rotate}
          border={16}
          style={{ left: HERO.left, top: HERO.top }}
        >
          <WordTag
            target="la mesa"
            meaning="the table"
            size={28}
            style={{ position: "absolute", left: tagLeft, top: tagTop }}
          />
        </Print>

        <Pasta src={farfalle} shape="farfalle" width={118} rotate={-14} style={{ left: 612, top: 492 }} />

        {/* Copy column */}
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            position: "absolute",
            left: 72,
            top: 64,
            width: 540,
            height: 502,
          }}
        >
          <Wordmark src={wordmark} width={196} />
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              marginTop: 34,
              fontFamily: ogFont.display,
              fontWeight: 800,
              fontSize: 92,
              lineHeight: 0.94,
              letterSpacing: -1.5,
              color: ogColors.ink,
            }}
          >
            <div style={{ display: "flex" }}>Learn the</div>
            <div style={{ display: "flex" }}>language of</div>
            <div style={{ display: "flex", color: ogColors.tomato }}>your day.</div>
          </div>
          <div
            style={{
              display: "flex",
              marginTop: 26,
              fontSize: 29,
              lineHeight: 1.3,
              color: ogColors.muted,
              maxWidth: 500,
            }}
          >
            Snap a moment. Learn the words inside it in Spanish or French.
          </div>
        </div>

        <div
          style={{
            display: "flex",
            position: "absolute",
            left: 72,
            bottom: 52,
            alignItems: "center",
            gap: 12,
            fontSize: 22,
            color: ogColors.tealDark,
          }}
        >
          <div
            style={{
              display: "flex",
              padding: "8px 16px",
              borderRadius: 999,
              background: ogColors.teal,
              color: ogColors.paper,
            }}
          >
            Free to start
          </div>
          <div style={{ display: "flex" }}>Spanish · French</div>
        </div>
      </div>
    ),
    { ...OG_SIZE, fonts },
  );
}
