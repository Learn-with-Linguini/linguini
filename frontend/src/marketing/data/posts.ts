export type PostCategory = "Company" | "Insights" | "Technical";

/** A looping video (main post only) or a real demo scene with its word labels. */
export type PostCover =
  | { kind: "video"; src: string; poster: string }
  | { kind: "photo"; scene: string; words: string[] }
  | { kind: "image"; src: string; alt: string };

export type Post = {
  slug: string;
  title: string;
  /** One or two sentences under the title and on cards. */
  summary: string;
  category: PostCategory;
  /** ISO date, YYYY-MM-DD. */
  date: string;
  readMinutes: number;
  cover: PostCover;
  /** Public path of a downloadable PDF version, when there is one. */
  pdf?: string;
};

// Newest first. The landing page shows the first three.
export const posts: Post[] = [
  {
    slug: "launch-week",
    title: "How we’re launching Linguini",
    summary:
      "Saturday 17 October, 3:01pm in Singapore. Our Product Hunt listing, every post we’ll publish, who we’re telling, the launch-day shifts and how we plan to keep the people who show up.",
    category: "Company",
    date: "2026-09-24",
    readMinutes: 10,
    cover: { kind: "video", src: "/blog/launch/cover-loop.mp4", poster: "/blog/launch/cover-loop-poster.jpg" },
    pdf: "/blog/launch-week.pdf",
  },
  {
    slug: "linguini-business-model",
    title: "The Linguini business model",
    summary:
      "Free for a daily photo, Plus when one a day isn’t enough. How we priced Linguini around learners, competitors and the AI cost of every lesson.",
    category: "Company",
    date: "2026-09-24",
    readMinutes: 7,
    cover: { kind: "video", src: "/blog/business-model.mp4", poster: "/blog/business-model-poster.jpg" },
    pdf: "/blog/linguini-business-model.pdf",
  },
  {
    slug: "why-we-teach-with-your-photos",
    title: "Why we teach with your photos",
    summary:
      "A word sticks when it belongs to a moment you lived. The idea behind Linguini’s photo lessons, and what happens inside one, step by step and cent by cent.",
    category: "Insights",
    date: "2026-09-24",
    readMinutes: 6,
    cover: { kind: "photo", scene: "golden-gate-bridge", words: ["bridge", "sea", "tower"] },
  },
  {
    slug: "linguini-vs-duolingo",
    title: "Linguini vs Duolingo, Babbel, Speak and CapWords",
    summary:
      "What each app teaches, what its free plan gives you and what a year costs, side by side. Plus the cases where Linguini is the wrong pick.",
    category: "Insights",
    date: "2026-09-20",
    readMinutes: 4,
    cover: { kind: "photo", scene: "desk-flatlay", words: ["laptop", "phone", "notebook"] },
  },
];

/** Old slugs that now live inside another post. */
export const movedPosts: Record<string, string> = {
  "inside-a-linguini-lesson": "why-we-teach-with-your-photos",
};

export function getPost(slug: string): Post | undefined {
  return posts.find(post => post.slug === slug);
}

const dateFormat = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  year: "numeric",
  timeZone: "UTC",
});

export function formatPostDate(value: string): string {
  return dateFormat.format(new Date(`${value}T00:00:00Z`));
}
