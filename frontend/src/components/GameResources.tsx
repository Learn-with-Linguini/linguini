import { InlineLoader } from "./LoadingScreen";
import { useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useGamification } from "../state/gamification";
import { gamificationKeys } from "../lib/gamification";
import { ApiError } from "../lib/api";
import { appearanceCommand, gameResourceKeys, getGameResources, selectAppearance } from "../lib/gameResources";
import type { Appearance, GameResourceSnapshot } from "../lib/gameResources";
import { friendlyError } from "../lib/queryKeys";
import { useAppState } from "../state/useAppState";
import { Button, Card } from "./ui";
import "./rooms.css";
import "./gamification.css";

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
  return <ResourceJar key={user?.id} {...props} />;
}

function ResourceJar({ shop = false, onChanged }: GameResourcesProps) {
  const { user } = useAppState();
  const client = useQueryClient();
  const progress = useGamification();
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
      if (user?.id) void client.invalidateQueries({ queryKey: gamificationKeys.account(user.id) });
      pending.current = null;
      setPendingAppearance(null);
      onChanged?.(updated);
    } catch (reason) {
      if (reason instanceof ApiError && reason.status >= 400 && reason.status < 500) { pending.current = null; setPendingAppearance(null); }
      setError(reason instanceof ApiError ? reason.message : friendlyError(reason));
    } finally { busyRef.current = false; setBusy(false); }
  };

  if (resources.isPending) return <InlineLoader compact label="Checking your Basil…" />;
  if (!resources.data) return <div className="stack-2"><p role="alert">We couldn’t check your Basil.</p>
    <Button variant="quiet" onClick={() => void resources.refetch()}>Try again</Button></div>;
  const data = resources.data;
  return <section className={`game-resources game-resources--${data.appearance}`} aria-label="Basil Points">
    <div className="game-resources__summary">
      <span className="game-resources__basil"><svg aria-hidden="true" viewBox="0 0 24 24" width="24" height="24"><path d="M20 3C9 2 3 7 5 14c2 7 13 5 15-11Z" fill="currentColor" /><path d="m3 21 12-12" stroke="var(--teal-dark)" strokeWidth="2" strokeLinecap="round" /></svg>
        <span><strong>{data.basilLeaves}</strong> Basil available</span></span>
    </div>
    {progress.data ? <div className="basil-totals"><div><strong>{progress.data.basil.today}</strong><span>Today’s Basil</span></div>
      <div><strong>{progress.data.basil.lifetime}</strong><span>Total Basil</span></div></div>
      : progress.isError ? <div><p role="alert">We couldn’t load your Basil totals.</p><Button variant="quiet" onClick={() => void progress.refetch()}>Retry totals</Button></div> : null}
    {shop ? <div className="stack game-resources__shop">

      <h3>Your jar</h3>
      <p className="small muted">Earn Basil Points as you practise. Each new accent costs 20 Basil. Your total earned stays the same when you spend Basil.</p>
      <div className="game-resources__accents">{accents.map(item => {
        const owned = item.appearance === "default" || data.ownedAppearances.includes(item.appearance);
        const selected = data.appearance === item.appearance;
        return <Card plain key={item.appearance} className={`game-resources__accent game-resources--${item.appearance}`}>
          <span className="game-resources__swatch" aria-hidden="true" /><strong>{item.label}</strong>
          <span className="small muted">{selected ? "Selected" : owned ? "Owned" : "20 Basil"}</span>
          <Button variant="secondary" disabled={selected || busy || Boolean(pendingAppearance) || (!owned && data.basilLeaves < 20)}
            onClick={() => void choose(item.appearance)}>{selected ? "Selected" : owned ? "Use accent" : "Get accent"}</Button>
        </Card>;
      })}</div>
      {error ? <div className="stack-2"><p role="alert">{error}</p>{pendingAppearance ?
        <Button variant="secondary" disabled={busy} onClick={() => void choose(pendingAppearance)}>Retry purchase</Button> : null}</div> : null}
      {busy ? <InlineLoader compact label="Saving your jar…" /> : null}
    </div> : null}
  </section>;
}
