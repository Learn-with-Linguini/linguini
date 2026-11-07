import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { getPractice } from "../lib/api";
import { trackAction } from "../lib/analytics.ts";
import {
  DAILY_CHALLENGE_PRIZES, countdownText, dailyChallengeKey, getDailyChallenge,
  scenePhotoPrompt, splitScenePhrase, timeLeft, wordShare,
} from "../lib/dailyChallenge";
import type { DailyChallenge as Challenge } from "../lib/dailyChallenge";
import { friendlyError } from "../lib/queryKeys";
import { sessionDestination } from "../lib/sessionRoute";
import { useAppState } from "../state/useAppState";
import { BasilIcon, CheckIcon, ClockIcon } from "./icons";
import { InlineLoader } from "./LoadingScreen";
import { Button } from "./ui";
import "./dailyChallenge.css";

const BOARD_ROWS = 8;
export const CHALLENGE_DETAILS_ID = "challenge-details";

function useNow(intervalMs = 15_000) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), intervalMs);
    return () => window.clearInterval(id);
  }, [intervalMs]);
  return now;
}

/** Full-bleed strip across the top of a challenge surface: what it is and how long is left. */
export function ChallengeTimer({ dayEndsAt, onEnded, label = "Daily challenge", compact = false }: { dayEndsAt: string; onEnded?: () => void; label?: string; compact?: boolean }) {
  const now = useNow();
  const { remaining, fraction, urgent } = timeLeft(dayEndsAt, now);
  useEffect(() => { if (remaining <= 0) onEnded?.(); }, [remaining, onEnded]);
  return <div className={`daily-challenge__timer${urgent ? " is-urgent" : ""}`}>
    {label ? <span className="daily-challenge__timer-label">{label}</span> : null}
    <time dateTime={dayEndsAt} className="daily-challenge__countdown"><ClockIcon size={16} />{urgent && !compact ? "Last hours · " : ""}{countdownText(remaining, compact)}</time>
    <span className="daily-challenge__drain" aria-hidden="true"><span style={{ transform: `scaleX(${fraction})` }} /></span>
  </div>;
}

export function ChallengeHeadline({ challenge, as: Heading = "h2", id, lede = true }: { challenge: Challenge; as?: "h1" | "h2"; id?: string; lede?: boolean }) {
  const [lead, place] = splitScenePhrase(challenge.scenePhrase, challenge.sceneTitle);
  return <>
    <Heading id={id} className="daily-challenge__title">Find words {lead}<span className="daily-challenge__place">{place}</span></Heading>
    {lede ? <p className="daily-challenge__lede">{scenePhotoPrompt(challenge.sceneTitle)}</p> : null}
  </>;
}

/** Reopens an unfinished challenge lesson at the learner's current step. */
export function useChallengeResume(sceneKey: string) {
  const navigate = useNavigate();
  const [resumeError, setResumeError] = useState<string | null>(null);
  const resume = async (sessionId: string) => {
    trackAction("daily_challenge_resumed", { sceneKey });
    setResumeError(null);
    try { navigate(sessionDestination(await getPractice(sessionId)).path); }
    catch (reason) { setResumeError(friendlyError(reason)); }
  };
  return { resume, resumeError };
}

/** The full ranking behind the top prize. */
export function ChallengePrizes() {
  return <div className="daily-challenge__prizes">
    <div className="daily-challenge__reward">
      <BasilIcon size={26} />
      <div className="daily-challenge__reward-copy">
        <strong>{DAILY_CHALLENGE_PRIZES[0].basil} Basil</strong>
        <span>Win today’s top prize</span>
      </div>
    </div>
    <ol>{DAILY_CHALLENGE_PRIZES.map(prize => <li key={prize.place}><span>{prize.place}</span><strong><BasilIcon size={18} />{prize.basil}<span className="visually-hidden"> Basil</span></strong></li>)}</ol>
  </div>;
}

export function ChallengeBoard({ challenge }: { challenge: Challenge }) {
  const hidden = challenge.words.length - BOARD_ROWS;
  return <div className="daily-challenge__board">
    <div className="daily-challenge__board-head">
      <h2>Community board</h2>
      <span>{challenge.participantCount} {challenge.participantCount === 1 ? "entry" : "entries"}</span>
    </div>
    {challenge.words.length ? <>
      <ol className="daily-challenge__words">{challenge.words.slice(0, BOARD_ROWS).map(word => <li key={word.label} className={word.foundByYou ? "is-yours" : undefined}>
        <span className="daily-challenge__bar" style={{ width: `${wordShare(word, challenge.words)}%` }} aria-hidden="true" />
        <strong>{word.label}</strong>
        {word.foundByYou ? <span className="daily-challenge__mine"><CheckIcon size={14} />Yours</span> : null}
        <span className="daily-challenge__count">{word.count}<span className="visually-hidden"> {word.count === 1 ? "learner" : "learners"}</span></span>
      </li>)}</ol>
      {hidden > 0 ? <p className="daily-challenge__more">+{hidden} more {hidden === 1 ? "word" : "words"} found today</p> : null}
    </> : <p className="daily-challenge__empty">No words yet. Yours could be first.</p>}
  </div>;
}

/** The Play page's summary; explanation, prizes and the board live on the challenge page. */
export function DailyChallenge() {
  const navigate = useNavigate();
  const { user } = useAppState();
  const query = useQuery({ queryKey: dailyChallengeKey(user?.id ?? ""), queryFn: ({ signal }) => getDailyChallenge(signal),
    enabled: Boolean(user?.id), refetchInterval: 30_000 });
  const data = query.data;
  const { resume, resumeError } = useChallengeResume(data?.sceneKey ?? "");
  if (query.isPending) return <div className="daily-challenge__pad"><InlineLoader label="Loading today’s challenge" /></div>;
  if (!data) return <div className="daily-challenge__pad"><p role="alert">We couldn’t load today’s challenge.</p>
    <Button variant="quiet" onClick={() => { trackAction("daily_challenge_retry_clicked"); void query.refetch(); }}>Retry challenge</Button></div>;
  return <section className="daily-challenge" aria-labelledby="daily-challenge-title">
    <ChallengeTimer dayEndsAt={data.dayEndsAt} onEnded={() => void query.refetch()} />
    <div className="daily-challenge__summary">
      <div className="daily-challenge__summary-heading">
        <ChallengeHeadline challenge={data} id="daily-challenge-title" lede={false} />
        <span className="pill pill--xp daily-challenge__prize"><BasilIcon size={16} />{DAILY_CHALLENGE_PRIZES[0].basil} Basil</span>
      </div>
      <div className="daily-challenge__actions">
        {data.status === "inProgress" && data.sessionId
          ? <Button onClick={() => void resume(data.sessionId!)}>Continue challenge</Button>
          : data.status !== "completed"
            ? <Button onClick={() => { trackAction("daily_challenge_start_clicked", { sceneKey: data.sceneKey }); navigate("/ispy/challenge"); }}>Join challenge</Button>
            : null}
        <Button variant="secondary" onClick={() => { trackAction("daily_challenge_details_clicked", { sceneKey: data.sceneKey }); navigate(`/ispy/challenge#${CHALLENGE_DETAILS_ID}`); }}>View rewards</Button>
      </div>
      {resumeError ? <p role="alert">{resumeError}</p> : null}
    </div>
    <div className="daily-challenge__play-board"><ChallengeBoard challenge={data} /></div>
  </section>;
}

/** A quiet Home reminder; the full challenge and board remain on Play. */
export function HomeDailyChallenge() {
  const navigate = useNavigate();
  const { user } = useAppState();
  const query = useQuery({ queryKey: dailyChallengeKey(user?.id ?? ""), queryFn: ({ signal }) => getDailyChallenge(signal),
    enabled: Boolean(user?.id), refetchInterval: 30_000 });
  const data = query.data;
  const { resume, resumeError } = useChallengeResume(data?.sceneKey ?? "");
  if (!data || data.status === "completed") return null;
  const open = () => {
    trackAction("home_daily_challenge_clicked", { sceneKey: data.sceneKey, status: data.status });
    if (data.status === "inProgress" && data.sessionId) void resume(data.sessionId);
    else navigate("/ispy/challenge");
  };
  // A filled teal card so the challenge stands apart from the cream dashboard.
  return <section className="home-daily-challenge" aria-labelledby="home-daily-challenge-title">
    <span className="home-daily-challenge__badge" aria-hidden="true"><BasilIcon size={26} /></span>
    <div className="home-daily-challenge__copy">
      <div className="home-daily-challenge__title-row">
        <h2 id="home-daily-challenge-title">Daily challenge</h2>
        <ChallengeTimer label="" compact dayEndsAt={data.dayEndsAt} onEnded={() => void query.refetch()} />
      </div>
      {data.sceneTitle ? <p className="home-daily-challenge__scene">{data.sceneTitle}</p> : null}
    </div>
    <Button variant="primary" onClick={open}>{data.status === "inProgress" ? "Continue" : "Join"}</Button>
    {resumeError ? <p role="alert">{resumeError}</p> : null}
  </section>;
}
