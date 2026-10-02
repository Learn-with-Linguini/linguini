/* eslint-disable @next/next/no-img-element -- Satori renders plain <img>, not next/image. */
import { ImageResponse } from "next/og";
import type { NextRequest } from "next/server";
import {
  IMMUTABLE_IMAGE_HEADERS,
  LANGUAGE_NAME,
  OG_SIZE,
  Pasta,
  Print,
  Tape,
  WordTag,
  Wordmark,
  journalTitle,
  loadImage,
  loadMascot,
  loadOgFonts,
  loadPasta,
  loadWordmark,
  ogColors,
  ogFont,
  parseJournalCard,
} from "@/lib/og";

export const runtime = "nodejs";

/**
 * Dynamic "journal page" social card.
 * GET /og?photo=<stem>&lang=es|fr&words=la mesa,la silla&title=<optional>
 * Output is a pure function of the (sanitised) query, so it is cached forever.
 */
export async function GET(request: NextRequest) {
  const q = request.nextUrl.searchParams;
  const card = parseJournalCard({
    photo: q.get("photo"),
    lang: q.get("lang"),
    words: q.get("words"),
    title: q.get("title"),
  });

  try {
    const [fonts, photoSrc, wordmark, mascot, penne] = await Promise.all([
      loadOgFonts(),
      loadImage(`public/photos/${card.photo.file}`),
      loadWordmark(),
      loadMascot(),
      loadPasta("penne"),
    ]);

    const title = journalTitle(card);
    const titleLength = Array.from(title).length;
    const titleSize = titleLength <= 26 ? 60 : titleLength <= 42 ? 50 : 42;
    // Keep title + chips inside the page: shrink chips as either grows.
    const crowded = card.words.length >= 4 || (card.words.length >= 3 && titleLength > 42);
    const chipSize = crowded ? 26 : card.words.length <= 2 ? 38 : 32;
    const chipGap = crowded ? 12 : 16;

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
          {/* The journal page: paper with faint rules and a margin line. */}
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              position: "absolute",
              left: 36,
              top: 30,
              width: 1128,
              height: 570,
              background: ogColors.paper,
              borderRadius: 28,
              border: `2px solid ${ogColors.line}`,
              boxShadow: "0 10px 28px rgba(86, 67, 34, 0.10)",
              overflow: "hidden",
            }}
          >
            {Array.from({ length: 11 }, (_, i) => (
              <div
                key={i}
                style={{
                  display: "flex",
                  position: "absolute",
                  left: 548,
                  right: 0,
                  top: 96 + i * 48,
                  height: 2,
                  background: "#f5eee0",
                }}
              />
            ))}
            <div
              style={{
                display: "flex",
                position: "absolute",
                left: 540,
                top: 0,
                bottom: 0,
                width: 2,
                background: "rgba(239, 91, 50, 0.28)",
              }}
            />
          </div>

          {/* Photo, taped into the page. */}
          <Print src={photoSrc} width={452} height={500} rotate={-3} border={16} style={{ left: 78, top: 62 }} />
          <Tape width={132} rotate={-7} style={{ left: 232, top: 44 }} />
          <Pasta src={penne} shape="penne" width={104} rotate={-24} style={{ left: 44, top: 470 }} />

          {/* Journal entry */}
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              position: "absolute",
              left: 612,
              top: 62,
              width: 510,
              height: 504,
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <img src={mascot} alt="" width={44} height={44} style={{ width: 44, height: 44 }} />
              <div style={{ display: "flex", fontSize: 24, color: ogColors.tealDark }}>
                {`My Linguini journal · ${LANGUAGE_NAME[card.lang]}`}
              </div>
            </div>

            <div
              style={{
                display: "flex",
                flexDirection: "column",
                justifyContent: "center",
                flexGrow: 1,
                paddingBottom: 12,
              }}
            >
              <div
                style={{
                  display: "flex",
                  fontFamily: ogFont.display,
                  fontWeight: 800,
                  fontSize: titleSize,
                  lineHeight: 1.02,
                  letterSpacing: -0.5,
                  color: ogColors.ink,
                }}
              >
                {title}
              </div>

              {card.words.length > 0 ? (
                <div style={{ display: "flex", flexWrap: "wrap", gap: chipGap, marginTop: crowded ? 22 : 28 }}>
                  {card.words.map((word) => (
                    <WordTag key={word} target={word} size={chipSize} />
                  ))}
                </div>
              ) : (
                <div style={{ display: "flex", marginTop: 24, maxWidth: 440, fontSize: 28, lineHeight: 1.3, color: ogColors.muted }}>
                  {`Snap a photo. Learn the words inside it in ${LANGUAGE_NAME[card.lang]}.`}
                </div>
              )}
            </div>

            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                paddingTop: 8,
              }}
            >
              <Wordmark src={wordmark} width={150} />
              <div style={{ display: "flex", fontSize: 21, color: ogColors.muted }}>Learn the language of your day.</div>
            </div>
          </div>
        </div>
      ),
      {
        ...OG_SIZE,
        fonts,
        headers: IMMUTABLE_IMAGE_HEADERS,
      },
    );
  } catch (error) {
    console.error("[og] failed to render journal card", error);
    return new Response("Failed to generate the image", {
      status: 500,
      headers: { "Cache-Control": "no-store" },
    });
  }
}
