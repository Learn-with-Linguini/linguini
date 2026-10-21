# Day One — LinkedIn video

Editable 30-second, 16:9 (1920 × 1080) HyperFrames composition for the
"Day One" social campaign in [`../../social/day-1/`](../../social/day-1).
Six scenes follow a learner's first day: morning hook → photo → word chips →
learner review ("AI suggests. You decide.") → two-way I-Spy → the real
Vocabulary screen showing words banked under each photo → public-beta CTA.

Structure and conventions mirror [`../linkedin-trailer/`](../linkedin-trailer):
persistent header + DAY ONE pill, dynamic bottom subtitle bar for muted
autoplay, progress bar, floating mascot, GSAP-driven scene cards.

## Assets

| File | Source |
| --- | --- |
| `assets/day-one-key-art.jpg` | Generated with OpenAI `gpt-image-1` (high), textless morning café flatlay |
| `assets/vocabulary.png` | Real app screenshot (`docs/screenshots/vocabulary.png`) |
| `assets/linguini-*.png`, fonts | Copied from `linkedin-trailer` |
| `audio/music.wav` | Reused trailer soundtrack |

## Commands

```sh
npm install
npx --yes hyperframes@0.8.181 preview --background   # Studio editor at :3002
npm run check                                        # lint + runtime + layout + motion + contrast
npm run render                                       # renders to renders/
```

## Editing

Open the Studio preview, click any element on the canvas to edit text,
drag or trim clips on the timeline, then Export or `npm run render`.
Scene timing lives in each `<section>`'s `data-start` / `data-duration`
and in the `scenes` array (subtitle text) inside `index.html`.
