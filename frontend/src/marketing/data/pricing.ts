/** Plans and prices. Read by the pricing section, the SoftwareApplication JSON-LD and /llms.txt. */
export const pricing = {
  currency: "USD",
  currentTier: "beta",
  beta: [
    "Unlimited photo lessons every day during the public beta",
    "Learn from your own photos or ready-made scenes",
    "Spanish, French and German, plus beginner Korean, from English",
    "Word cards, I-Spy and sentence games",
    "Vocabulary progress, streaks and Basil",
    "No payment card required",
  ],
  plusMonthly: 7.99,
  plusYearly: 49.99,
  foundingYearly: 34.99,
  foundingSeats: 300,
  trialDays: 7,
  free: [
    "One new photo lesson every day",
    "Unlimited replays of our curated scenes",
    "Spanish, French and German, plus beginner Korean, from English",
    "Word cards, I-Spy and sentence games",
    "Streaks, Basil and your pasta avatar",
  ],
  plus: [
    "Up to 10 photo lessons a day",
    "Pronunciation feedback when you speak",
    "Review mode for words that haven’t stuck yet",
    "Early access to new languages",
  ],
} as const;

export const yearlyPerMonth = (pricing.plusYearly / 12).toFixed(2);
export const yearlySaving = Math.round((1 - pricing.plusYearly / (pricing.plusMonthly * 12)) * 100);
