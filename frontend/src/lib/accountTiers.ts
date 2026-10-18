import type { AccountTier } from "./api";

type AccountTierDetails = {
  label: string;
  description: string;
  allowance: string;
};

export const accountTiers: Record<AccountTier, AccountTierDetails> = {
  beta: {
    label: "Beta",
    description: "Public beta access",
    allowance: "Unlimited photo lessons every day during the beta",
  },
  free: {
    label: "Free",
    description: "Free plan",
    allowance: "Photo lessons and friend challenges",
  },
  plus: {
    label: "Plus",
    description: "Plus plan",
    allowance: "More photo lessons and premium learning tools",
  },
};
