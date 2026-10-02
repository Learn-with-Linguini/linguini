/**
 * Copy for the launch campaign post. The social posts here are the drafts we will publish;
 * marketing/product-hunt/social-posts.md holds the same text for pasting.
 */

export const LAUNCH = {
  date: "2026-10-17",
  pacific: "Sat 17 Oct, 00:01 PDT",
  singapore: "Sat 17 Oct, 3:01pm SGT",
  landing: "linguini-landing.vercel.app",
};

const IMG = "/blog/launch";

export const productHunt = {
  name: "Linguini",
  tagline: "Explore language lessons hidden in everyday photos",
  description:
    "Explore photo scenes in Spanish or French through word cards, I-Spy and sentence games, then finish with a journal page. Try a complete interactive mini session in your browser and tell us what should make the leap into the learner app.",
  topics: ["Language Learning", "Education", "Productivity"],
  gallery: [
    { src: `${IMG}/01-your-world.jpg`, alt: "Gallery 1: See a scene. Learn its language." },
    { src: `${IMG}/02-find-your-words.jpg`, alt: "Gallery 2: words pinned to a hillside street." },
    { src: `${IMG}/03-play-and-build.jpg`, alt: "Gallery 3: an I-Spy clue and a sentence builder." },
    { src: `${IMG}/04-keep-the-day.jpg`, alt: "Gallery 4: the lesson saved as a journal page." },
  ],
  firstComment: [
    "Hi Product Hunt! We’re the team behind Linguini. We kept noticing that the words we wanted to learn were already in front of us: the café table, the view on a walk, the things on our desk. So we built a language app around those moments.",
    "Today you can try a full mini session on our site in Spanish or French. Pick a scene, explore its words, play I-Spy and sentence games, and watch it become a journal page. Then sign up and the app does the same with a photo you take: AI reads the picture, pins the words and builds the games.",
    "We’d love specific feedback: which part helped a word stick, and what would bring you back tomorrow? Tell us which scene you picked and where you got stuck. We’re in the comments all day.",
  ],
};

export type XPostData = { text: string; image?: { src: string; alt: string } };

export const xThread: XPostData[] = [
  {
    text: "Linguini is live on Product Hunt today 🍝\n\nPick a photo of a street, a café or a desk. Linguini pins the Spanish or French words onto it, you play a round of I-Spy with them, and the lesson ends as a page in your journal.\n\nIt’s early. Tell us where you got stuck 👇",
    image: { src: `${IMG}/launch-card-1200x630.jpg`, alt: "Link card: Live on Product Hunt today. Point at your day. Learn the words." },
  },
  {
    text: "Why photos? A word sticks when it belongs to a place you remember. A flashcard has no place. Your camera roll is full of them.",
  },
  {
    text: "Built by a small student team at NUS. Spanish and French for now, free to try in your browser, nothing to install.\n\nThe listing, with the 50-second explainer: [PH_POST_URL]",
  },
];

export const instagram = {
  slides: [
    { src: `${IMG}/ig-post-1080x1350.jpg`, alt: "Today’s lesson is on your camera roll, over a café photo labelled la mesa and el taburete." },
    { src: `${IMG}/social-square.jpg`, alt: "A photo scene. A fresh lesson. Hillside drive, el coche." },
    { src: `${IMG}/countdown-1080x1080.jpg`, alt: "3 days to launch, over a hillside street labelled la casa, el coche and la flor." },
  ],
  caption:
    "Today’s lesson is on your camera roll 📷\n\nLinguini is live on Product Hunt. Pick a photo, learn the words inside it in Spanish or French, play a round of I-Spy and keep the day as a journal page.\n\nLink in bio. What’s the first thing you’d photograph?",
  tags: "#learnspanish #learnfrench #languagelearning #studygram #producthunt",
  story: [
    { src: `${IMG}/ig-story-countdown-1080x1920.jpg`, alt: "Story 1: 3 days to launch." },
    { src: `${IMG}/ig-story-1080x1920.jpg`, alt: "Story 2: We’re live on Product Hunt today." },
  ],
};

export const linkedin = {
  author: "Madrid Lim",
  role: "Co-maker of Linguini · NUS Computing",
  text: "We put Linguini on Product Hunt today.\n\nIt started as a CS3216 project with a simple bet: vocabulary lists are easy to forget, but the places you walk through every day are not. So Linguini starts with a photo, pins Spanish or French words onto it, and ends each lesson as a journal page.\n\nThe browser demo needs no account, and the app turns a photo you take into a lesson, with AI finding the words in it.\n\nIf you teach, learn or build things, I’d value one honest comment on the listing: which step would make you come back tomorrow?",
  image: { src: `${IMG}/linkedin-1584x396.jpg`, alt: "Your photo is the lesson. Launching on Product Hunt, Sat 17 Oct." },
};

export const reddit = {
  sub: "r/Spanish",
  flair: "Weekly self-promotion thread",
  title: "We made a photo-based Spanish mini lesson. Does the photo actually help you remember?",
  text: "Small student team here. The idea: learn words from a place you recognise (a street, a café), then use them in I-Spy and a short sentence before saving it as a journal page. There’s a free demo with ready-made scenes, no sign-up, and the app does the same with your own photos. We’re trying to work out if the photo helps recall or just looks nice. If you try one scene, what would you change?",
};

export const telegram = {
  group: "NUS CS3216 / Computing friends",
  text: "hey all! our CS3216 app Linguini just went up on Product Hunt 🍝 you pick a photo and learn the Spanish or French words in it. takes a few minutes in the browser. if you try it, drop a comment on what confused you 🙏",
  image: { src: `${IMG}/launch-card-1200x630.jpg`, alt: "Launch-day card: Live on Product Hunt today." },
};

export const banners = [
  { src: `${IMG}/x-header-1500x500.jpg`, name: "X header", size: "1500 × 500", use: "Profile header from T−7. Text sits top-left because the avatar covers the bottom-left." },
  { src: `${IMG}/linkedin-1584x396.jpg`, name: "LinkedIn cover", size: "1584 × 396", use: "Our personal profiles and the page. Copy starts right of the logo." },
  { src: `${IMG}/launch-card-1200x630.jpg`, name: "Launch-day link card", size: "1200 × 630", use: "Sent as a photo in Telegram, WhatsApp and Discord on the day." },
  { src: `${IMG}/countdown-1080x1080.jpg`, name: "Countdown square", size: "1080 × 1080", use: "Feed and stories at T−3." },
  { src: `${IMG}/ig-post-1080x1350.jpg`, name: "Instagram launch post", size: "1080 × 1350", use: "4:5 takes the most room in the feed." },
  { src: `${IMG}/ig-story-countdown-1080x1920.jpg`, name: "Countdown story", size: "1080 × 1920", use: "T−3 story. Same safe areas as the launch story." },
  { src: `${IMG}/ig-story-1080x1920.jpg`, name: "Launch story", size: "1080 × 1920", use: "Top 250 px and bottom 340 px left clear for the UI and the link sticker." },
];
