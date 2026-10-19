import { useId } from "react";
import { useQuery } from "@tanstack/react-query";
import { gamificationKeys, getMissionProgress, jarMessage, type MissionBatch } from "../lib/gamification";
import { gameResourceKeys, getGameResources, type Appearance } from "../lib/gameResources";
import { useAppState } from "../state/useAppState";
import { useGamification } from "../state/gamification";
import { Button } from "./ui";
import { BasilIcon } from "./icons";
import { MissionIllustration } from "./MissionIllustration";
import "./gamification.css";

export function SauceJar({ batch, name, appearance = "default" }: { batch: MissionBatch; name?: string; appearance?: Appearance }) {
  const clipId = useId();
  const ready = batch.status === "ready";
  return <div className={`mission-jar${ready ? " mission-jar--ready" : ""}`}>
    {ready ? <span className="mission-jar__badge" aria-hidden="true"><MissionIllustration missionId={batch.missionId} /></span> :
      <svg width="48" height="64" viewBox="0 0 48 64" aria-hidden="true">
        <defs><clipPath id={clipId}><rect x="6" y="14" width="36" height="44" rx="9" /></clipPath></defs>
        <rect x="6" y="14" width="36" height="44" rx="9" fill="var(--cream)" stroke="var(--teal-dark)" strokeWidth="2" />
        <g clipPath={`url(#${clipId})`}><rect x="7" y={58 - batch.percent * .43} width="34" height={batch.percent * .43} fill="var(--tomato)" />
          {batch.percent >= 25 ? <><circle cx="16" cy="51" r="4" fill="var(--pasta)" /><circle cx="31" cy="44" r="3" fill="var(--pasta)" /></> : null}
          {batch.percent >= 75 ? <path d="m12 32 7-3m7 8 7-4" stroke="var(--teal-dark)" strokeWidth="3" strokeLinecap="round" /> : null}
          {batch.percent >= 90 ? <><circle cx="20" cy="24" r="2" fill="var(--butter)" /><circle cx="31" cy="21" r="2" fill="var(--butter)" /></> : null}
        </g><rect x="9" y="7" width="30" height="8" rx="3" fill={appearance === "herb" ? "var(--teal-dark)" : appearance === "pasta" ? "var(--pasta)" : "var(--tomato)"} stroke="var(--teal-dark)" strokeWidth="2" />
      </svg>}
    <div>{name ? <p className="small muted">{name}</p> : null}<strong>{ready ? "Mission complete" : "Sauce Jar"} · {batch.percent}%</strong>
      <p>{jarMessage(batch)}</p>
      <span className="small muted">{batch.assessedQuestions} of {batch.totalQuestions} questions checked</span>
      {batch.status === "review" ? <ul className="small">{batch.requirements.map(item => <li key={item}>{item}</li>)}</ul> : null}
    </div>
  </div>;
}

export function MissionProgress({ sessionId, missionId }: { sessionId: string; missionId?: string | null }) {
  const { user } = useAppState();
  const summary = useGamification();
  const resources = useQuery({ queryKey: gameResourceKeys(user?.id ?? ""),
    queryFn: ({ signal }) => getGameResources(signal), enabled: Boolean(user?.id) });
  const progress = useQuery({ queryKey: gamificationKeys.mission(user?.id ?? "", sessionId),
    queryFn: ({ signal }) => getMissionProgress(sessionId, signal), enabled: Boolean(user?.id), refetchInterval: 30_000 });
  if (progress.isError) return <div className="small"><p role="alert">We couldn’t load your mission progress.</p>
    <Button variant="quiet" onClick={() => void progress.refetch()}>Retry progress</Button></div>;
  return <>{progress.data?.filter(batch => !missionId || batch.missionId === missionId).map(batch =>
    <SauceJar key={`${batch.missionId}:${batch.practiceLevel}:${batch.contentVersion}`} batch={batch} appearance={resources.data?.appearance}
      name={summary.data?.missions.find(mission => mission.missionId === batch.missionId)?.name} />)}</>;
}

export function QuestionBasil({ amount }: { amount?: number }) {
  return amount && amount > 0 ? <strong className="question-basil" role="status"><BasilIcon size={17} />+{amount} Basil earned</strong> : null;
}
