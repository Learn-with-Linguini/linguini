import { BusinessModelCanvas } from "../diagrams";
import { BreakEven } from "../story/BreakEven";
import { CostVideo } from "../story/CostVideo";
import { CompareApps, ModelMap, PlanMatrix } from "../story/figures";
import { InView } from "../story/InView";
import { PriceStory } from "../story/PriceStory";
import story from "../story/story.module.css";
import s from "../article.module.css";

type Column = { label: string; num?: boolean };

/**
 * A plain table: the first cell of each row is its heading. On narrow screens each row stacks,
 * with the column name beside each value.
 */
function DataTable({ columns, rows, caption }: { columns: Column[]; rows: string[][]; caption?: string }) {
  return (
    <figure className={s.fig}>
      <table className={s.table}>
        <thead>
          <tr>
            {columns.map(col => <th key={col.label} scope="col" className={col.num ? s.num : undefined}>{col.label}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map(([head, ...cells]) => (
            <tr key={head}>
              <th scope="row">{head}</th>
              {cells.map((cell, i) => (
                <td key={i} data-label={columns[i + 1].label} className={columns[i + 1].num ? s.num : undefined}>{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {caption ? <figcaption>{caption}</figcaption> : null}
    </figure>
  );
}

const modelChoices = {
  columns: [{ label: "Call" }, { label: "Chosen, via OpenRouter" }, { label: "Main alternatives" }, { label: "Why" }],
  rows: [
    ["Scene analysis", "Claude Haiku 4.5 (Anthropic)", "GPT-4o, GPT-4.1-mini", "Best quality, found every object we labelled, and the only model the app accepted every time."],
    ["Translation", "GPT-4o-mini (OpenAI)", "Mistral Small, Claude Haiku 4.5", "Nearly as good as Mistral at the same price, without the throttling Mistral hit."],
    ["Learning tasks", "GPT-5.4-mini (OpenAI)", "GPT-4.1-mini, Gemini 3.5 Flash-Lite", "The only model that reliably fits our lesson format. Also our most expensive call."],
    ["I-Spy clues", "Gemini 3.1 Flash-Lite (Google)", "GPT-4o-mini, Claude Haiku 4.5", "The best clues, in perfect target language, and it never gave the answer away."],
    ["I-Spy guesses", "GPT-4.1-mini (OpenAI)", "Gemini 3.5 Flash-Lite, GPT-4o-mini", "The most accurate at working out which object a learner meant."],
  ],
};

const learnerCosts = {
  columns: [{ label: "Learner" }, { label: "Photo lessons a month" }, { label: "Chosen models", num: true }, { label: "Cheapest alternatives", num: true }],
  rows: [
    ["Free, light", "2", "$0.04", "$0.02"],
    ["Free, casual", "8", "$0.17", "$0.07"],
    ["Free, every day", "30", "$0.64", "$0.27"],
    ["Plus, typical", "30, with speaking", "$0.74", "$0.37"],
    ["Plus, heavy", "90", "$2.17", "$1.06"],
    ["Plus, 10 a day, every day", "300", "$7.13", "$3.47"],
  ],
};

const streams = {
  columns: [{ label: "Stream" }, { label: "Price" }, { label: "When" }, { label: "Why" }],
  rows: [
    ["Plus", "$49.99 a year or $7.99 a month", "At launch", "The core. Sold on the web, so no app store takes a cut."],
    ["Founding Plus", "$34.99 a year, first 300 members", "Launch, until 300 members or 31 Dec 2026", "Early revenue from people who will tell us what to build. Each nets about $2.74 a month against $1.03 in AI."],
    ["Family plan", "About $79.99 a year for up to 4", "Once retention is proven", "Every member uses AI, so we price per seat instead of copying Duolingo’s $119.99 for 6."],
    ["Classroom licences", "Not set", "Year two", "A teacher sets a daily scene and the class journals about it."],
    ["Printed journal", "Needs a print quote", "Once PDF export ships", "A one-off purchase that fits the idea of keeping the day."],
  ],
};

const stages = {
  columns: [{ label: "Stage" }, { label: "The question" }, { label: "What we measure" }, { label: "Money coming in" }],
  rows: [
    ["Now, in beta", "Does it stick?", "New learners who take a second photo lesson within a week", "None. The beta costs us about $75 a month, which we treat as research."],
    ["Launch year", "Will people pay?", "300 Founding Plus members", "Plus and Founding Plus"],
    ["After that", "Does it scale?", "4.5% of monthly learners paying", "Plus, then family plans, classrooms and printed journals"],
  ],
};

export function BusinessModel() {
  return (
    <div className={`${s.body} ${s.document}`}>
      <InView as="p" className={story.lede}>
        Free gives every learner <mark>one photo lesson and one journal page a day</mark>. Plus is{" "}
        <mark>$49.99 a year</mark> for anyone who wants more. Each photo lesson costs us about <mark>2¢ in AI</mark>, so
        the free tier pays for itself once enough people upgrade: <mark>about 4% of learners</mark> on the models we chose,
        or under 2% once cheaper models pass our tests.
      </InView>

      <h2 id="at-a-glance">The model at a glance</h2>
      <p>
        The free plan limits the one thing that costs us money: AI reading your own photos. The learning stays free.
      </p>
      <BusinessModelCanvas />

      <h2 id="who">Who it is for</h2>
      <p>
        Our learners are people returning to a language they half know, beginners who want a few minutes a day, and
        students and travellers. None of them want to sit through a course, and most will never pay for one: across
        education apps, only 2.3% of downloads turn into a paid subscription.
      </p>
      <p>
        So the free plan has to be good enough to become a habit on its own, and the reason to upgrade has to show up
        at the moment someone wants more. For us that moment is easy to spot. It is the day you take more photos than
        one lesson covers.
      </p>

      <h2 id="plans">Plans</h2>
      <PlanMatrix />
      <p>
        Curated scenes are analysed once in advance, so replaying one costs us about a sixth of a cent and free learners
        can play them all day. Plus adds the things that cost us money: more photo lessons, more photos per journal page
        and feedback on your speaking.
      </p>
      <p>
        Founding is Plus for our first 300 members, at $34.99 a year for as long as they stay. We give up some margin on
        them. In return we get early payers who tell us what to build, and in the first year that is worth more than the
        margin.
      </p>

      <h2 id="price">How we set the price</h2>
      <p>
        There are three usual ways to price something: from what it costs you, from what competitors charge, and from
        what it is worth to the customer. We checked $49.99 all three ways.
      </p>
      <PriceStory />

      <h3>Against the competition</h3>
      <CompareApps />
      <p>
        CapWords is cheaper, but it stops at flashcards. The course apps do more teaching and charge nearly twice as much. We sit
        between them, so our price does too. From Duolingo we took the shape of the free tier: keep it genuinely useful,
        limit how much you can do, and save the expensive AI for paid plans.
      </p>

      <h2 id="costs">What a lesson costs us</h2>
      <CostVideo />

      <h3 id="which-model">Which model runs each call</h3>
      <p>
        Every call goes through OpenRouter, with one key, and each call has its own setting. We picked each model by
        running the candidates through the app’s own prompts and checks: 14 labelled photos, 17 translations, 6 scenes
        and 22 learner guesses. No provider won everywhere, so we use three. That has a second benefit: if one provider
        goes down, one feature falls back to its alternative and the rest of the app carries on.
      </p>
      <DataTable {...modelChoices} caption="Chosen after our model comparison. Temperature is 0 for every call, because raising it made every call worse." />

      <h3 id="per-learner">What a learner costs</h3>
      <p>
        A lesson costs about 2¢, so what a learner costs us depends on how much they use Linguini. The table shows a
        month for different kinds of learner.
      </p>
      <DataTable {...learnerCosts} caption="AI and storage per learner per month, at OpenRouter prices. The cheapest alternatives are not ready yet: they score lower in our tests." />
      <p>
        After Stripe’s fees, a Plus learner brings in about $5.24 a month. The typical payer is comfortably profitable,
        and so is the heavy one. We only lose money on someone who uses all ten lessons every day.
        That is why Plus stops at ten a day instead of promising “unlimited”: unlimited means losing money on your most
        enthusiastic learners.
      </p>
      <p>
        Hosting is fixed at $52–70 a month (Vercel, Supabase and Render), and at every size we modelled it is smaller
        than the AI bill. So our costs grow with use, not with signups, and the daily limits are what keep them in check.
        Stripe also keeps 3.4% + 50¢ of each payment, which is why we push the annual plan.
      </p>

      <h2 id="model-choice">Why freemium</h2>
      <p>
        Ordinary software costs almost nothing to run for one more user. AI doesn’t: every lesson is a bill. Many AI
        companies charge less than cost and bet that models will get cheaper. We can’t make that bet. A cheaper model only
        helps if it still makes a good lesson, and in our tests the cheapest ones did not, yet. The pricing has to work at
        the costs we actually face.
      </p>
      <p>We judged each option on two questions: does it cover the AI cost, and will learners like it?</p>
      <ModelMap />

      <h2 id="scale">Does the free tier pay for itself?</h2>
      <p>
        Every payer also carries the free learners: about 42 of them when 2.3% pay. On the models we chose, that only
        pays off once about 4% of learners pay, so our target is 4.5%, enough to cover AI and hosting from 5,000 learners a month. The cheapest
        alternatives would break even at under 2%, but they make worse lessons today, so we launch on the chosen models
        and work on bringing the cost down.<span className="no-print"> Drag the sliders to try other numbers.</span>
      </p>
      <BreakEven />
      <p>
        Before a wide launch we will do three things. First, fix the defect in our lesson format that makes most models
        fail it, so the lesson generator can move to GPT-4.1-mini at less than half the cost. Second, run the cheapest
        alternatives through the same evaluation and switch only the calls that pass. Third, enforce the daily limits on
        the server and track what every lesson costs.
      </p>

      <h2 id="revenue">Where the money comes from</h2>
      <p>
        Plus is the business. Everything else either brings in money early or comes later, once we know learners stay.
      </p>
      <DataTable {...streams} />

      <h2 id="success">What success looks like, stage by stage</h2>
      <p>
        Revenue is the wrong measure for a product nobody comes back to. In the beta, one learner who returns tells us
        more than one who pays once and leaves. So the number we watch changes as the question changes: first whether
        people come back, then whether they pay, then whether enough of them pay to carry everyone else.
      </p>
      <DataTable {...stages} />

      <h2 id="sources">Sources</h2>
      <p className={s.muted} style={{ fontSize: 14 }}>
        <a href="https://openrouter.ai/models">OpenRouter model prices</a> ·{" "}
        <a href="https://supabase.com/pricing">Supabase</a> · <a href="https://vercel.com/pricing">Vercel</a> ·{" "}
        <a href="https://stripe.com/pricing">Stripe</a> ·{" "}
        <a href="https://www.sec.gov/Archives/edgar/data/0001562088/000162828026053299/q2fy26duolingo6-30x26share.htm">Duolingo Q2 2026 letter</a> ·{" "}
        <a href="https://www.dealnews.com/features/duolingo/cost/">Duolingo prices</a> ·{" "}
        <a href="https://www.dealnews.com/features/babbel/plan-pricing/">Babbel prices</a> ·{" "}
        <a href="https://speakshark.com/blog/speak-app-pricing-per-month-2026">Speak prices</a> ·{" "}
        <a href="https://apps.apple.com/us/app/capwords-ai-photo-vocabulary/id6738896465">CapWords</a> ·{" "}
        <a href="https://www.revenuecat.com/state-of-subscription-apps-2026-education">RevenueCat SOSA 2026</a> ·{" "}
        <a href="https://www.italki.com/en/blog/spanish-tutor-cost">italki tutor costs</a>. Token counts and quality
        scores come from our model comparison, which ran every candidate through the app’s own prompts, schemas and
        validators.
      </p>
    </div>
  );
}
