import { useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { gamificationKeys, getChefStandings, setChefParticipation } from "../lib/gamification";
import { trackAction } from "../lib/analytics.ts";
import { useAppState } from "../state/useAppState";
import { BasilIcon, TrophyIcon } from "./icons";
import { InlineLoader } from "./LoadingScreen";
import { Button } from "./ui";
import "./gamification.css";
import "./leaderboard.css";

export function ChefOfTheDay() {
  const { user } = useAppState();
  const client = useQueryClient();
  const key = gamificationKeys.chefs(user?.id ?? "");
  const pending = useRef(false);
  const query = useQuery({ queryKey: key, queryFn: ({ signal }) => getChefStandings(signal), enabled: Boolean(user?.id),
    refetchInterval: () => pending.current ? false : 60_000,
    refetchOnWindowFocus: () => !pending.current, refetchOnReconnect: () => !pending.current });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [retryChoice, setRetryChoice] = useState<boolean | null>(null);
  const participate = async (value: boolean) => {
    if (pending.current) return;
    pending.current = true; setSaving(true); setError(null); setRetryChoice(value);
    trackAction("chef_of_the_day_participation_toggled", { participating: value });
    try {
      await client.cancelQueries({ queryKey: key, exact: true });
      client.setQueryData(key, await setChefParticipation(value));
      setRetryChoice(null);
      void client.invalidateQueries({ queryKey: key, exact: true });
    }
    catch { setError("We couldn’t save your choice. Please try again."); }
    finally { pending.current = false; setSaving(false); }
  };
  const data = query.data;
  return <section className="stack" aria-labelledby="chef-day-title">
    <div className="ispy-chefs__heading"><div><span>Today’s Basil leaderboard</span><h2 id="chef-day-title">Chefs of the Day</h2></div><TrophyIcon size={30} /></div>
    {query.isPending ? <InlineLoader label="Loading today’s chefs…" /> : !data ? <div><p role="alert">We couldn’t load today’s leaderboard.</p>
      <Button variant="quiet" onClick={() => { trackAction("chef_of_the_day_retry_clicked"); void query.refetch(); }}>Retry leaderboard</Button></div> : <>
      <section className="ispy-chefs__comparison" aria-label="Your leaderboard position">
        <div><span>Your place</span><strong>#{data.currentRank ?? "—"}</strong></div>
        <div><span>Your Basil</span><strong>{data.todayBasil}</strong></div>
        <p>{!data.participating ? "Join today’s board to show your progress." : data.currentRank === 1 ? "You’re leading today!" : data.currentRank ? `${data.basilToNextRank ?? 0} Basil to reach the next position.` : "Your first Basil today will put you on the board."}</p>
      </section>
      {error ? <p role="alert">{error}</p> : null}
      {data.top.length ? <ol className="ispy-chefs__list" aria-label="Today’s chefs">{data.top.map((entry, index) => <li key={`${entry.rank}:${index}`} className="ispy-chefs__entry">
        <span className="ispy-chefs__rank">{entry.rank}</span><img className="leaderboard-avatar" src={`/pasta-assets/${entry.avatar}.png`} alt="" /><strong>{entry.displayName}</strong>
        <span className="ispy-chefs__basil"><BasilIcon size={17} />{entry.basil} Basil</span></li>)}</ol> : <p className="muted">A fresh day in the kitchen. There’s room for everyone.</p>}
      <Button variant="secondary" disabled={saving} onClick={() => void participate(retryChoice ?? !data.participating)}>{saving ? "Saving…" : retryChoice !== null ? "Retry choice" : data.participating ? "Leave the leaderboard" : "Join Chef of the Day"}</Button>
      <p className="small muted">Today ends {new Date(data.dayEndsAt).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}. Your total Basil stays with you.</p>
    </>}
  </section>;
}
