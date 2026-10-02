/** Plans and prices. Read by the pricing section, the SoftwareApplication JSON-LD and /llms.txt. */
export const pricing = {
  currency: "USD",
  plusMonthly: 7.99,
  plusYearly: 49.99,
  foundingYearly: 34.99,
  foundingSeats: 300,
  trialDays: 7,
  free: [
    "One new photo lesson every day",
    "One journal page a day",
    "Unlimited replays of our curated scenes",
    "Spanish and French, from English",
    "Word cards, I-Spy and sentence games",
    "Streaks, XP and your pasta avatar",
  ],
  plus: [
    "Up to 10 photo lessons a day",
    "Pronunciation feedback when you speak",
    "Review mode for words that haven’t stuck yet",
    "Up to 10 photos in each journal entry",
    "Export your journal as a PDF keepsake",
    "Early access to new languages",
  ],
} as const;

export const yearlyPerMonth = (pricing.plusYearly / 12).toFixed(2);
export const yearlySaving = Math.round((1 - pricing.plusYearly / (pricing.plusMonthly * 12)) * 100);
