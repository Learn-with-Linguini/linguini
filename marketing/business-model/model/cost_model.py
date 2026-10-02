"""Linguini unit-economics model.

Run from any directory with: python3 marketing/business-model/model/cost_model.py
Standard library only. Writes marketing/business-model/model/unit-economics.json and prints
the tables used in marketing/business-model/README.md.

Model choices and token counts come from the backend's model comparison (MODEL_COMPARISON.md
and backend/evals/model_comparison/results/summary_full.csv): every candidate ran through the
production services, and the tokens below are the measured means per call. Prices are the
OpenRouter catalogue (provider list price) from that comparison's snapshot; every AI call is
routed through OpenRouter, so they are also what we pay.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

OUT = Path(__file__).resolve().parent / "unit-economics.json"

# --- Provider prices through OpenRouter, USD per 1M tokens -------------------------
# https://openrouter.ai/models (catalogue snapshot in MODEL_COMPARISON.md, "Model facts")
PRICES = {
    "anthropic/claude-haiku-4.5": (1.00, 5.00),
    "openai/gpt-4o": (2.50, 10.00),
    "openai/gpt-4o-mini": (0.15, 0.60),
    "openai/gpt-4.1-mini": (0.40, 1.60),
    "openai/gpt-5.4-mini": (0.75, 4.50),
    "google/gemini-3.1-flash-lite": (0.25, 1.50),
    "google/gemini-3.5-flash-lite": (0.30, 2.50),
    "mistralai/mistral-small-2603": (0.15, 0.60),
}
MODERATION_PER_IMAGE = 0.0  # omni-moderation-latest is free
TRANSCRIBE_PER_MIN = 0.003  # gpt-4o-mini-transcribe
AZURE_PRON_PER_HOUR = 1.32 + 0.30  # Azure real-time STT + pronunciation add-on (conservative)
TTS_PER_M_CHARS = 12.00  # gpt-4o-mini-tts; browser speechSynthesis is free and used today

# --- Tokens per call ------------------------------------------------------------
# tokens_in / out_expected: measured means from the model comparison (image tokens and any
# reasoning tokens included). out_cap: the output caps in backend/app/ai/registry.py
# (1,500 default; 4,000 for learning tasks), billed in the worst case.


@dataclass(frozen=True)
class Call:
    feature: str
    model: str
    tokens_in: int
    out_expected: int
    out_cap: int
    calls_expected: float = 1
    calls_worst: float = 1


PIPELINES = ("chosen", "fallback", "budget")
PIPELINE_LABELS = {
    "chosen": "Chosen models (backend/.env.example)",
    "fallback": "First alternative for every call",
    "budget": "Cheapest usable alternative",
}

# Measured tokens per (feature, model): input, output.
TOKENS = {
    ("scene", "anthropic/claude-haiku-4.5"): (3375, 664),
    ("scene", "openai/gpt-4o"): (2298, 427),
    ("scene", "openai/gpt-4.1-mini"): (2781, 604),
    ("translation", "openai/gpt-4o-mini"): (648, 216),
    ("translation", "mistralai/mistral-small-2603"): (421, 294),
    ("tasks", "openai/gpt-5.4-mini"): (2831, 1597),
    ("tasks", "openai/gpt-4.1-mini"): (2833, 1872),
    ("clues", "google/gemini-3.1-flash-lite"): (938, 124),
    ("clues", "openai/gpt-4o-mini"): (1057, 76),
    ("guess", "openai/gpt-4.1-mini"): (1025, 70),
    ("guess", "google/gemini-3.5-flash-lite"): (1201, 72),
    ("guess", "openai/gpt-4o-mini"): (1025, 62),
}

MODELS = {
    # chosen: backend/.env.example after MODEL_COMPARISON.md.
    "chosen": {"scene": "anthropic/claude-haiku-4.5", "translation": "openai/gpt-4o-mini", "tasks": "openai/gpt-5.4-mini",
               "clues": "google/gemini-3.1-flash-lite", "guess": "openai/gpt-4.1-mini"},
    # fallback: the first "main alternative" for each call, used if the chosen provider fails.
    "fallback": {"scene": "openai/gpt-4o", "translation": "mistralai/mistral-small-2603", "tasks": "openai/gpt-4.1-mini",
                 "clues": "openai/gpt-4o-mini", "guess": "google/gemini-3.5-flash-lite"},
    # budget: the cheapest alternative the app still accepted in the comparison. Lower quality: see README.
    "budget": {"scene": "openai/gpt-4.1-mini", "translation": "openai/gpt-4o-mini", "tasks": "openai/gpt-4.1-mini",
               "clues": "openai/gpt-4o-mini", "guess": "openai/gpt-4o-mini"},
}

FEATURES = (
    ("scene", "Scene analysis (vision)", 1500, 1, 1),
    ("translation", "Translation", 1500, 1, 1),
    ("tasks", "Learning tasks", 4000, 1, 1),
    ("clues", "I-Spy clues", 1500, 1, 1),
    ("guess", "I-Spy guess feedback", 1500, 3, 5),
)


def session_calls(pipeline: str) -> list[Call]:
    """Calls for one own-photo session on the given pipeline."""
    calls = []
    for key, label, cap, expected, worst in FEATURES:
        model = MODELS[pipeline][key]
        tokens_in, out = TOKENS[(key, model)]
        calls.append(Call(label, model, tokens_in, out, cap, expected, worst))
    return calls


JOURNAL_FEEDBACK = Call("Journal feedback (planned)", "openai/gpt-4o-mini", 1500, 500, 1500)
RETRY_EXPECTED, RETRY_WORST = 1.10, 2.0  # MAX_RETRIES=1 can double a call


def call_cost(call: Call, worst: bool) -> float:
    price_in, price_out = PRICES[call.model]
    out = call.out_cap if worst else call.out_expected
    n = call.calls_worst if worst else call.calls_expected
    retry = RETRY_WORST if worst else RETRY_EXPECTED
    return n * retry * (call.tokens_in * price_in + out * price_out) / 1e6


def session_cost(pipeline: str, worst: bool) -> float:
    return MODERATION_PER_IMAGE + sum(call_cost(c, worst) for c in session_calls(pipeline))


# A curated (preloaded) scene is analysed once offline, so only guesses are live.
def curated_session_cost(pipeline: str, worst: bool) -> float:
    return call_cost(session_calls(pipeline)[-1], worst)


# Pronunciation: ~15 spoken attempts x 4 s = 1 minute of audio per session.
PRON_SECONDS = 60
PRON_OPTIONS = {
    "Browser speech recognition": 0.0,
    "gpt-4o-mini-transcribe + text compare": TRANSCRIBE_PER_MIN * PRON_SECONDS / 60 + 0.0003,
    "Azure pronunciation assessment": AZURE_PRON_PER_HOUR * PRON_SECONDS / 3600,
}

# --- Storage and bandwidth --------------------------------------------------------
# https://supabase.com/pricing and .../manage-your-usage/storage-size
STORAGE_PER_GB_MONTH = 0.0213  # after 100 GB on Pro
EGRESS_PER_GB = 0.09  # after 250 GB on Pro
MB_STORED_PER_PHOTO = 3.0  # phone JPEG + derivatives; uploads are capped at 10 MB
MB_SERVED_PER_SESSION = 1.5  # signed derivative views during a session

# --- Fixed monthly infrastructure -------------------------------------------------
# Vercel Hobby is non-commercial, so charging users requires Pro ($20/seat).
# Supabase Pro $25 includes Micro compute and 100k MAU. Render Starter $7 / Standard $25.
FIXED = {
    "launch": {"Vercel Pro (landing + app)": 20, "Supabase Pro": 25, "Render Starter API": 7},
    "growth": {"Vercel Pro (landing + app)": 20, "Supabase Pro": 25, "Render Standard API": 25},
}

# --- Payment fees -----------------------------------------------------------------
# Stripe as served to our Singapore account: 3.4% + $0.50, +0.5% international card,
# Billing 0.7%. App stores: 15% (Apple Small Business Program, Google Play subs).


def net_web(price: float) -> float:
    return price * (1 - 0.034 - 0.005 - 0.007) - 0.50


def net_store(price: float) -> float:
    return price * 0.85


# --- Usage profiles, sessions per month -------------------------------------------
@dataclass(frozen=True)
class Profile:
    name: str
    photo_sessions: int
    curated_sessions: int
    journals: int
    spoken_sessions: int


PROFILES = [
    Profile("Free · light", 2, 2, 2, 0),
    Profile("Free · casual", 8, 4, 8, 0),
    Profile("Free · at daily cap", 30, 10, 30, 0),
    Profile("Plus · typical", 30, 10, 30, 30),
    Profile("Plus · heavy (3/day)", 90, 20, 30, 90),
    Profile("Plus · fair-use ceiling (10/day)", 300, 30, 30, 300),
]


BROWSER, TRANSCRIBE, AZURE = PRON_OPTIONS


def profile_cost(p: Profile, pipeline: str, worst: bool, pron: str = TRANSCRIBE) -> float:
    ai = p.photo_sessions * session_cost(pipeline, worst)
    ai += p.curated_sessions * curated_session_cost(pipeline, worst)
    ai += p.journals * call_cost(JOURNAL_FEEDBACK, worst)
    ai += p.spoken_sessions * PRON_OPTIONS[pron]
    storage = p.photo_sessions * MB_STORED_PER_PHOTO / 1024 * STORAGE_PER_GB_MONTH
    egress = (p.photo_sessions + p.curated_sessions) * MB_SERVED_PER_SESSION / 1024 * EGRESS_PER_GB
    return ai + storage + egress


# Free users: 50% light, 35% casual, 15% at the daily cap (mean ≈ 8 photo sessions).
# Payers: 80% typical, 20% heavy. Free users speak through the browser at no cost.
FREE_MIX = ((0, 0.50), (1, 0.35), (2, 0.15))
PLUS_MIX = ((3, 0.80), (4, 0.20))


def free_user_cost(pipeline: str) -> float:
    return sum(w * profile_cost(PROFILES[i], pipeline, False, BROWSER) for i, w in FREE_MIX)


def plus_user_cost(pipeline: str) -> float:
    return sum(w * profile_cost(PROFILES[i], pipeline, False) for i, w in PLUS_MIX)


# --- Pricing options ---------------------------------------------------------------
OPTIONS = {
    "A · Current landing ($6.99 / $59.88)": (6.99, 59.88),
    "B · Recommended ($7.99 / $49.99)": (7.99, 49.99),
    "Founding Plus ($34.99/yr, capped cohort)": (None, 34.99),
}
RECOMMENDED = "B · Recommended ($7.99 / $49.99)"
ANNUAL_SHARE = 0.59  # RevenueCat SOSA 2026, education plan mix


def monthly_net_arpu(monthly: float | None, annual: float, channel=net_web) -> float:
    if monthly is None:
        return channel(annual) / 12
    return ANNUAL_SHARE * channel(annual) / 12 + (1 - ANNUAL_SHARE) * channel(monthly)


# --- Scale scenarios ----------------------------------------------------------------
# Conversion: RevenueCat education download-to-paid median 2.3%; Duolingo's paid
# penetration of MAU (12.7M / 140.6M ≈ 9%) is a mature-product ceiling. From launch
# we plan on TARGET_CONVERSION, the paid share that covers AI and hosting at 5,000+ MAU.
TARGET_CONVERSION = 0.045
SCENARIOS = [
    ("Beta", 300, 0.023, "launch"),
    ("Launch year", 5_000, TARGET_CONVERSION, "launch"),
    ("Traction", 50_000, TARGET_CONVERSION, "growth"),
]


def scenario(mau: int, conversion: float, fixed_key: str, pipeline: str, option: str = RECOMMENDED):
    monthly, annual = OPTIONS[option]
    payers = mau * conversion
    free_cost = (mau - payers) * free_user_cost(pipeline)
    plus_cost = payers * plus_user_cost(pipeline)
    fixed = sum(FIXED[fixed_key].values())  # Supabase Pro includes 100k MAU
    revenue = payers * monthly_net_arpu(monthly, annual)
    cost = free_cost + plus_cost + fixed
    return {
        "mau": mau,
        "conversion": conversion,
        "payers": round(payers),
        "net_revenue": round(revenue, 2),
        "free_ai_cost": round(free_cost, 2),
        "plus_ai_cost": round(plus_cost, 2),
        "fixed": fixed,
        "total_cost": round(cost, 2),
        "contribution": round(revenue - cost, 2),
    }


def breakeven_conversion(pipeline: str, option: str = RECOMMENDED) -> float:
    """Paid share of MAU at which net revenue covers all variable AI cost."""
    monthly, annual = OPTIONS[option]
    arpu, free, plus = monthly_net_arpu(monthly, annual), free_user_cost(pipeline), plus_user_cost(pipeline)
    # c * (arpu - plus) = (1 - c) * free  ->  c = free / (arpu - plus + free)
    return free / (arpu - plus + free)


def main():
    result = {"pipelines": {p: {"label": PIPELINE_LABELS[p], "models": MODELS[p]} for p in PIPELINES},
              "sessions": {}, "breakdown": {}, "profiles": {}, "options": {}, "scenarios": {}, "breakeven_conversion": {}}

    print("Per own-photo session (USD)")
    for pipeline in PIPELINES:
        for worst in (False, True):
            label = f"{pipeline}, {'worst case' if worst else 'expected'}"
            value = session_cost(pipeline, worst)
            result["sessions"][label] = round(value, 5)
            print(f"  {label:32} ${value:.4f}")
        result["breakdown"][pipeline] = {c.feature: round(call_cost(c, False), 5) for c in session_calls(pipeline)}
    for pipeline in PIPELINES:
        print(f"  breakdown · {pipeline}")
        for feature, value in result["breakdown"][pipeline].items():
            print(f"    {feature:28} ${value:.4f}")
    result["curated_session"] = round(curated_session_cost("chosen", False), 5)
    result["journal_feedback"] = round(call_cost(JOURNAL_FEEDBACK, False), 5)
    result["pronunciation_per_session"] = {k: round(v, 5) for k, v in PRON_OPTIONS.items()}
    print(f"  curated scene session           ${result['curated_session']:.4f}")
    print(f"  journal feedback                ${result['journal_feedback']:.4f}")
    for name, value in PRON_OPTIONS.items():
        print(f"  pronunciation · {name:38} ${value:.4f}")

    print("\nMonthly variable cost per user")
    for p in PROFILES:
        spoken = p.spoken_sessions > 0
        row = {
            pipeline: round(profile_cost(p, pipeline, False, TRANSCRIBE if spoken else BROWSER), 3)
            for pipeline in PIPELINES
        }
        row["worst"] = round(profile_cost(p, "chosen", True, AZURE if spoken else BROWSER), 3)
        result["profiles"][p.name] = row
        print(f"  {p.name:34} " + "  ".join(f"{k} ${v:5.2f}" for k, v in row.items()))
    for pipeline in PIPELINES:
        result["profiles"].setdefault("_mix", {})[pipeline] = {
            "free": round(free_user_cost(pipeline), 3), "plus": round(plus_user_cost(pipeline), 3)
        }
    print(f"  blended free/plus: {result['profiles']['_mix']}")

    print("\nNet revenue per paying user per month (web / app store)")
    for name, (monthly, annual) in OPTIONS.items():
        web = monthly_net_arpu(monthly, annual, net_web)
        store = monthly_net_arpu(monthly, annual, net_store)
        result["options"][name] = {"monthly": monthly, "annual": annual, "net_web": round(web, 2), "net_store": round(store, 2)}
        print(f"  {name:44} web ${web:4.2f}   store ${store:4.2f}")

    print("\nScenarios (option B)")
    for pipeline in PIPELINES:
        for label, mau, conv, fixed_key in SCENARIOS:
            row = scenario(mau, conv, fixed_key, pipeline)
            result["scenarios"].setdefault(pipeline, {})[label] = row
            print(f"  {pipeline:13} {label:12} {row}")

    print("\nBreak-even paid conversion (variable AI cost only)")
    for pipeline in PIPELINES:
        for option in OPTIONS:
            if OPTIONS[option][0] is None:
                continue
            c = breakeven_conversion(pipeline, option)
            result["breakeven_conversion"].setdefault(pipeline, {})[option] = round(c, 4)
            print(f"  {pipeline:13} {option:40} {c:.1%}")

    OUT.write_text(json.dumps(result, indent=2))
    print(f"\nWrote {OUT.name}")


if __name__ == "__main__":
    main()
