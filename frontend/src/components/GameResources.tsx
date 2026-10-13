import { useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError } from "../lib/api";
import { appearanceCommand, gameResourceKeys, gameResourcesEnabled, getGameResources, selectAppearance, saucePercent } from "../lib/gameResources";
import type { Appearance, GameResourceSnapshot } from "../lib/gameResources";
import { friendlyError } from "../lib/queryKeys";
import { useAppState } from "../state/useAppState";
import { Button, Card } from "./ui";
import "./rooms.css";

export interface GameResourcesProps {
  shop?: boolean;
  onChanged?: (resources: GameResourceSnapshot) => void;
}

const accents: { appearance: Appearance; label: string }[] = [
  { appearance: "default", label: "Original jar" },
  { appearance: "herb", label: "Herb accent" },
  { appearance: "pasta", label: "Pasta accent" },
];

export function GameResources(props: GameResourcesProps) {
  const { user } = useAppState();
  if (!gameResourcesEnabled) return null;
  return <EnabledGameResources key={user?.id} {...props} />;
}

function EnabledGameResources({ shop = false, onChanged }: GameResourcesProps) {
  const { user } = useAppState();
  const client = useQueryClient();
  const key = gameResourceKeys(user?.id ?? "");
  const resources = useQuery({ queryKey: key, queryFn: ({ signal }) => getGameResources(signal), enabled: Boolean(user?.id),
    refetchInterval: 60_000, refetchOnWindowFocus: true });
  const pending = useRef<{ appearance: Appearance; commandId: string } | null>(null);
  const [pendingAppearance, setPendingAppearance] = useState<Appearance | null>(null);
  const busyRef = useRef(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const choose = async (appearance: Appearance) => {
    if (busyRef.current) return;
    busyRef.current = true;
    setBusy(true);
    setError(null);
    const command = appearanceCommand(appearance, pending.current);
    pending.current = command;
    setPendingAppearance(command.appearance);
    try {
      const updated = await selectAppearance(command.appearance, command.commandId);
      client.setQueryData(key, updated);
      pending.current = null;
      setPendingAppearance(null);
      onChanged?.(updated);
    } catch (reason) {
      if (reason instanceof ApiError && reason.status >= 400 && reason.status < 500) { pending.current = null; setPendingAppearance(null); }
      setError(reason instanceof ApiError ? reason.message : friendlyError(reason));
    } finally { busyRef.current = false; setBusy(false); }
  };

  if (resources.isPending) return <p className="small muted" role="status">Checking your Sauce…</p>;
  if (!resources.data) return <div className="stack-2"><p role="alert">We couldn’t check your Sauce.</p>
    <Button variant="quiet" onClick={() => void resources.refetch()}>Try again</Button></div>;
  const data = resources.data;
  const refill = new Date(data.sauce.refillsAt);
  const refillText = Number.isNaN(refill.getTime()) ? "at your next daily refill" :
    new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit", month: "short", day: "numeric" }).format(refill);

  return <section className={`game-resources game-resources--${data.appearance}`} aria-label="Sauce and Basil leaves">
    <div className="game-resources__summary">
      <div className="game-resources__jar" aria-hidden="true"><span style={{ height: `${saucePercent(data.sauce)}%` }} /></div>
      <div className="game-resources__amount">
        <strong>Sauce <span>{data.sauce.remaining} / {data.sauce.capacity}</span></strong>
        <div className="game-resources__track" role="meter" aria-label="Sauce remaining" aria-valuemin={0}
          aria-valuemax={data.sauce.capacity} aria-valuenow={data.sauce.remaining}>
          <span style={{ width: `${saucePercent(data.sauce)}%` }} />
        </div>
        <span className="small muted">Refills {refillText}</span>
      </div>
      <span className="game-resources__basil"><svg aria-hidden="true" viewBox="0 0 24 24" width="24" height="24"><path d="M20 3C9 2 3 7 5 14c2 7 13 5 15-11Z" fill="currentColor" /><path d="m3 21 12-12" stroke="var(--teal-dark)" strokeWidth="2" strokeLinecap="round" /></svg>
        <span><strong>{data.basilLeaves}</strong> Basil leaves</span></span>
    </div>
    {shop ? <div className="stack game-resources__shop">
      <p className="small muted">A new lesson or room uses 1 Sauce. Resuming and repeated actions don’t use more; failed setup returns Sauce. Mistakes never drain extra Sauce.</p>
      <h3>Your jar</h3>
      <p className="small muted">Collect Basil leaves as you practise. Each new accent costs 20 leaves.</p>
      <div className="game-resources__accents">{accents.map(item => {
        const owned = item.appearance === "default" || data.ownedAppearances.includes(item.appearance);
        const selected = data.appearance === item.appearance;
        return <Card plain key={item.appearance} className={`game-resources__accent game-resources--${item.appearance}`}>
          <span className="game-resources__swatch" aria-hidden="true" /><strong>{item.label}</strong>
          <span className="small muted">{selected ? "Selected" : owned ? "Owned" : "20 Basil leaves"}</span>
          <Button variant="secondary" disabled={selected || busy || Boolean(pendingAppearance) || (!owned && data.basilLeaves < 20)}
            onClick={() => void choose(item.appearance)}>{selected ? "Selected" : owned ? "Use accent" : "Get accent"}</Button>
        </Card>;
      })}</div>
      {error ? <div className="stack-2"><p role="alert">{error}</p>{pendingAppearance ?
        <Button variant="secondary" disabled={busy} onClick={() => void choose(pendingAppearance)}>Retry purchase</Button> : null}</div> : null}
      {busy ? <p role="status">Saving your jar…</p> : null}
    </div> : null}
  </section>;
}
