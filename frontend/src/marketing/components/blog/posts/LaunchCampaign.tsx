import Link from "../../Link";
import { SoundVideo } from "../../SoundVideo";
import { LaunchClock, ProductHuntListing } from "../launch/Figures";
import { Img } from "../launch/Img";
import {
  Circles, Communities, CreatorMap, DayShifts, GrowthCurve, Phases, PlanStrip, ProductHuntAsks, ReturnDots,
  Roles,
} from "../launch/Plan";
import l from "../launch/launch.module.css";
import p from "../launch/plan.module.css";
import { InView } from "../story/InView";
import story from "../story/story.module.css";
import s from "../article.module.css";

const IMG = "/blog/launch";

export function LaunchCampaign() {
  return (
    <div className={s.body}>
      <InView as="p" className={story.lede}>
        A launch is one day. Keeping the people who show up takes <mark>the two weeks after</mark>, so that’s where most
        of this plan goes. Here it is in the order it happens.
      </InView>

      <PlanStrip />

      <h2 id="when">When we launch</h2>
      <p>
        Product Hunt ranks launches on a daily leaderboard, and its day starts at midnight in San Francisco. Launch at
        12:01am Pacific and you get all 24 hours. Launch later and you’re behind products that started at midnight.
      </p>
      <LaunchClock />
      <p>
        Most of Product Hunt’s audience is in the US and Europe, so the busiest hours fall inside their daytime.
        That’s why launch day runs in shifts.
      </p>
      <p>
        We chose <strong>Tuesday 20 October</strong>: the start of Product Hunt’s week, so the listing gets the longest
        runway on the weekly leaderboard, and the middle of the week has about three times as many launches. A small
        team gets more attention at the quieter edges.
      </p>

      <h2 id="soft-launch">Soft launch first, then open doors</h2>
      <p>
        A soft launch means letting a few people in before everyone else. Clubhouse stayed invite-only for 16 months and
        Arc for over a year, and the scarcity made people want in. The price is people. Arc’s CEO has said{" "}
        <a href="https://youtu.be/xJdx0BlP0iY?t=198">they lost up to 80% of sign-ups to their waitlist</a>.
      </p>
      <p>We want the useful part, feedback from a small group, without the waitlist. So we do both, one after the other:</p>
      <Phases />
      <p>
        The beta finds the bugs while mistakes are cheap. On launch day there’s nothing to wait for, which matters twice:
        Product Hunt doesn’t feature products people can’t get into straight away, and Show HN rejects anything behind a
        waitlist.
      </p>

      <h2 id="listing">The listing</h2>
      <p>
        Product Hunt is backed by Y Combinator, and it’s where Notion, Obsidian, Otter and BeReal launched. It asks for
        five things. Here’s what we’re giving it.
      </p>
      <ProductHuntAsks />
      <ProductHuntListing />
      <p>
        The tagline says what you can do in the demo in the first minute. The first comment ends on two questions,
        because people answer questions. Product Hunt says 70% of its Product of the Day, Week and Month winners had a
        first comment from the maker.
      </p>
      <figure className={s.fig}>
        <div className="no-print">
          <SoundVideo
            poster={`${IMG}/explainer-poster.jpg`}
            label="Linguini explainer: a photo becomes Spanish or French words, a game and a journal page"
            captions={`${IMG}/explainer.vtt`}
            sources={[{ src: `${IMG}/explainer-720p.mp4` }]}
          />
        </div>
        <Img src={`${IMG}/explainer-poster.jpg`} alt="Explainer video poster frame" className={`print-only ${l.videoPoster}`} loading="eager" />
        <figcaption>
          The 50-second explainer for the listing. It starts muted with captions, because most people scroll with the
          sound off. Tap Sound on to hear the voiceover.
        </figcaption>
      </figure>
      <p>
        A listing only works if people see it. Product Hunt doesn’t send you traffic so much as reward the traffic you
        bring, so the next question is who we tell.
      </p>

      <h2 id="who">Who we’re telling, closest first</h2>
      <p>
        We go out in circles. The closer someone is to us, the earlier they try it and the more honest we expect them
        to be. Strangers only hear about it once the people who know us have found the worst bugs.
      </p>
      <Circles />

      <h3>Communities</h3>
      <p>We want as much reach as we can get, but every community has rules, and getting banned reaches nobody.</p>
      <Communities />
      <p>
        One pair we won’t pitch: Steve Kaufmann and Ikenna run LingQ and Fluyo, and asking a competitor to feature us is
        awkward for everyone.
      </p>

      <h3>Creators</h3>
      <p>
        The obvious move is to email the biggest channel. But a huge channel gets hundreds of pitches, and a small one
        reads every email.
      </p>
      <CreatorMap />

      <h2 id="day">Launch day, hour by hour</h2>
      <p>
        The leaderboard keeps moving for the full 24 hours, and its busiest stretch is the US and European daytime. So
        the four of us split the day into three shifts, Pacific time.
      </p>
      <DayShifts />
      <p>Whoever is on shift covers three jobs:</p>
      <Roles />
      <p className={s.note}>
        <strong>If sign-up breaks:</strong> we stop posting, put a note on the landing page and send people to the demo,
        which needs no account, while we fix it.
      </p>

      <h2 id="after">After launch day</h2>
      <p>
        By Sunday afternoon the votes stop counting. Visits and upvotes tell you whether the listing worked, not whether
        the product did. For that we’re watching one number: <strong>of the people who sign up during launch week, how
        many do a second lesson within seven days?</strong>
      </p>
      <ReturnDots />
      <p>
        Is 10% good? <a href="https://amplitude.com/blog/7-percent-retention-rule">Amplitude</a> makes the analytics
        software thousands of apps use to count their users, so it can see how most apps do. We’re not competing with
        it. We’re borrowing its ruler:
      </p>
      <table className={p.table}>
        <thead>
          <tr><th scope="col">New users still active on day 7</th><th scope="col">Share</th></tr>
        </thead>
        <tbody>
          <tr><th scope="row">Enough to be in the top quarter of apps, per Amplitude</th><td>7%</td></tr>
          <tr><th scope="row">Our target for launch week</th><td>10%</td></tr>
        </tbody>
      </table>
      <p>
        So 10% is ambitious, and with numbers this small one person either way changes everything. But it answers the
        question we actually have: does the loop bring anyone back at all? Here’s how we try to earn the second visit:
      </p>
      <ul>
        <li><strong>No account for the first lesson.</strong> The demo is the onboarding.</li>
        <li><strong>Every lesson ends with picking tomorrow’s scene</strong>, so there’s a reason to open it again.</li>
        <li><strong>One reminder on day two</strong>, only if you opted in, using your own photo. Not a daily blast.</li>
        <li><strong>A streak from day one</strong>, and a weekly recap of your journal: the week’s photos and words on one page.</li>
      </ul>
      <p>
        Then we act on what we see. On day 1 we fix the onboarding bugs people hit on launch day. On day 3 we talk to five
        people who came back and five who didn’t. On day 7 we count second lessons and fix the biggest drop-off. On day
        14 we publish what we learned, with the real numbers.
      </p>

      <h2 id="next">The next launch</h2>
      <p>
        Launches are spikes. Users jump on the day, then drift down to a plateau. If you wait until the line is flat to
        plan the next thing, you’ve waited too long.
      </p>
      <GrowthCurve />
      <p>
        So the second launch is already picked: <strong>two-way description practice</strong>. Linguini is built around
        photo-led language descriptions and doesn’t grade them yet. When it does, that’s worth a relaunch, which Product Hunt allows after a
        major update, and we’ll arrive with our week-one numbers. What we charge, and what each lesson costs us, is in{" "}
        <Link href="/blog/linguini-business-model">our business model</Link>.
      </p>

      <h2 id="sources">Sources</h2>
      <p className={s.muted} style={{ fontSize: 14 }}>
        <a href="https://www.ycombinator.com/">Y Combinator</a> ·{" "}
        <a href="https://www.producthunt.com/topics/artificial-intelligence">Product Hunt AI launches</a> ·{" "}
        <a href="https://www.producthunt.com/launch/preparing-for-launch">Product Hunt: preparing for launch</a> ·{" "}
        <a href="https://www.producthunt.com/launch">Product Hunt launch guide</a> ·{" "}
        <a href="https://help.producthunt.com/en/articles/479557-how-to-post-a-product">How to post a product</a> ·{" "}
        <a href="https://www.producthunt.com/launch/sharing-your-launch">Sharing your launch</a> ·{" "}
        <a href="https://help.producthunt.com/en/articles/9883485-product-hunt-featuring-guidelines">Featuring guidelines</a> ·{" "}
        <a href="https://www.producthunt.com/p/databox/i-ve-analyzed-all-2026-ph-launches-to-find-the-best-day-to-launch">Databox: best day to launch in 2026</a> ·{" "}
        <a href="https://news.ycombinator.com/showhn.html">Show HN guidelines</a> ·{" "}
        <a href="https://youtu.be/xJdx0BlP0iY?t=198">Arc’s CEO on the waitlist</a> ·{" "}
        <a href="https://techcrunch.com/2023/07/25/arc-browser-is-now-available-to-download-for-everyone">Arc opens to everyone</a> ·{" "}
        <a href="https://en.wikipedia.org/wiki/Clubhouse_(app)">Clubhouse</a> ·{" "}
        <a href="https://www.hellotalk.com/community-guidelines">HelloTalk guidelines</a> ·{" "}
        <a href="https://lindiebotes.com/about/">Lindie Botes</a> ·{" "}
        <a href="https://amplitude.com/blog/7-percent-retention-rule">Amplitude 7% rule</a>.
        Subreddit rules and community sizes change often; we recheck each one the week before.
      </p>
    </div>
  );
}
