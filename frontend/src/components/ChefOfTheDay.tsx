import { useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { gamificationKeys, getChefStandings, setChefParticipation } from "../lib/gamification";
import { trackAction } from "../lib/analytics.ts";
import { useAppState } from "../state/useAppState";
import { Button, Card } from "./ui";
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
  return <section className="stack" aria-labelledby="chef-day-title"><h2 id="chef-day-title">Chef of the Day</h2>
    <p>Earn Basil and climb today’s kitchen leaderboard.</p>
    {query.isPending ? <p role="status">Loading today’s kitchen…</p> : !data ? <div><p role="alert">We couldn’t load today’s leaderboard.</p>
      <Button variant="quiet" onClick={() => { trackAction("chef_of_the_day_retry_clicked"); void query.refetch(); }}>Retry leaderboard</Button></div> : <>
      <Card plain><div className="basil-totals"><div><strong>{data.todayBasil}</strong><span>Today’s Basil</span></div>
        <div><strong>{data.personalBest}</strong><span>Personal best</span></div></div>
        {data.participating ? <p>{data.currentRank ? `You’re #${data.currentRank} today.` : "Your first Basil today will put you on the board."}
          {data.basilToNextRank ? ` Earn ${data.basilToNextRank} more Basil to reach the next position.` : null}</p> :
          <p className="small">Joining is optional. Your profile name and today’s Basil will appear on the board.</p>}
        <Button variant="secondary" disabled={saving} onClick={() => void participate(retryChoice ?? !data.participating)}>{saving ? "Saving…" : retryChoice !== null ? "Retry choice" : data.participating ? "Leave the leaderboard" : "Join Chef of the Day"}</Button>
      </Card>
      {error ? <p role="alert">{error}</p> : null}
      {data.top.length ? <ol className="chef-standings" aria-label="Today’s chefs">{data.top.map((entry, index) => <li key={`${entry.rank}:${index}`}>
        <strong>#{entry.rank}</strong><img className="leaderboard-avatar" src={`/pasta-assets/${entry.avatar}.png`} alt="" /><span>{entry.displayName}</span><strong>{entry.basil} Basil</strong></li>)}</ol> : <p className="muted">A fresh day in the kitchen. There’s room for everyone.</p>}
      <p className="small muted">Today ends {new Date(data.dayEndsAt).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}. Your total Basil stays with you.</p>
    </>}
  </section>;
}
