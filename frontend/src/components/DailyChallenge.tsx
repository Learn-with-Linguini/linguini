import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { getPractice } from "../lib/api";
import { trackAction } from "../lib/analytics.ts";
import {
  DAILY_CHALLENGE_PRIZES, countdownText, dailyChallengeKey, getDailyChallenge,
  lastResultText, splitScenePhrase, timeLeft, wordShare,
} from "../lib/dailyChallenge";
import type { DailyChallenge as Challenge } from "../lib/dailyChallenge";
import { friendlyError } from "../lib/queryKeys";
import { sessionDestination } from "../lib/sessionRoute";
import { useAppState } from "../state/useAppState";
import { BasilIcon, CameraIcon, CheckIcon, ClockIcon, TrophyIcon } from "./icons";
import { InlineLoader } from "./LoadingScreen";
import { Button } from "./ui";
import "./dailyChallenge.css";

const BOARD_ROWS = 8;

function useNow(intervalMs = 15_000) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), intervalMs);
    return () => window.clearInterval(id);
  }, [intervalMs]);
  return now;
}

/** Full-bleed strip across the top of a challenge surface: what it is and how long is left. */
export function ChallengeTimer({ dayEndsAt, onEnded }: { dayEndsAt: string; onEnded?: () => void }) {
  const now = useNow();
  const { remaining, fraction, urgent } = timeLeft(dayEndsAt, now);
  useEffect(() => { if (remaining <= 0) onEnded?.(); }, [remaining, onEnded]);
  return <div className={`daily-challenge__timer${urgent ? " is-urgent" : ""}`}>
    <span className="daily-challenge__timer-label">Today’s Treasure Hunt Challenge</span>
    <time dateTime={dayEndsAt} className="daily-challenge__countdown"><ClockIcon size={16} />{urgent ? "Last hours · " : ""}{countdownText(remaining)}</time>
    <span className="daily-challenge__drain" aria-hidden="true"><span style={{ transform: `scaleX(${fraction})` }} /></span>
  </div>;
}

export function ChallengeHeadline({ challenge, as: Heading = "h2", id }: { challenge: Challenge; as?: "h1" | "h2"; id?: string }) {
  const [lead, place] = splitScenePhrase(challenge.scenePhrase, challenge.sceneTitle);
  return <>
    <Heading id={id} className="daily-challenge__title">Find words {lead}<span className="daily-challenge__place">{place}</span></Heading>
    <p className="daily-challenge__lede">Take a photo, do the lesson, and add it to today’s shared board.</p>
  </>;
}

export function DailyChallenge() {
  const navigate = useNavigate();
  const { user } = useAppState();
  const [resumeError, setResumeError] = useState<string | null>(null);
  const query = useQuery({ queryKey: dailyChallengeKey(user?.id ?? ""), queryFn: ({ signal }) => getDailyChallenge(signal),
    enabled: Boolean(user?.id), refetchInterval: 30_000 });
  const data = query.data;
  if (query.isPending) return <div className="daily-challenge__pad"><InlineLoader label="Loading today’s challenge" /></div>;
  if (!data) return <div className="daily-challenge__pad"><p role="alert">We couldn’t load today’s challenge.</p>
    <Button variant="quiet" onClick={() => { trackAction("daily_challenge_retry_clicked"); void query.refetch(); }}>Retry challenge</Button></div>;
  const resume = async (sessionId: string) => {
    trackAction("daily_challenge_resumed", { sceneKey: data.sceneKey });
    setResumeError(null);
    try { navigate(sessionDestination(await getPractice(sessionId)).path); }
    catch (reason) { setResumeError(friendlyError(reason)); }
  };
  const result = lastResultText(data.lastResult);
  const hidden = data.words.length - BOARD_ROWS;
  return <section className="daily-challenge" aria-labelledby="daily-challenge-title">
    <ChallengeTimer dayEndsAt={data.dayEndsAt} onEnded={() => void query.refetch()} />
    <div className="daily-challenge__body">
      <div className="daily-challenge__join">
        <ChallengeHeadline challenge={data} id="daily-challenge-title" />
       
        <div className="daily-challenge__prizes">
          <ol>{DAILY_CHALLENGE_PRIZES.map(prize => <li key={prize.place}><span>{prize.place}</span><strong><BasilIcon size={18} />{prize.basil}<span className="visually-hidden"> Basil</span></strong></li>)}</ol>
        </div>
        {data.status === "completed"
          ? <p className="daily-challenge__done"><CheckIcon size={20} /><span>You’re on the board with {data.yourWordCount} {data.yourWordCount === 1 ? "word" : "words"}. Bonuses land when the day ends.</span></p>
          : data.status === "inProgress" && data.sessionId
            ? <Button block onClick={() => void resume(data.sessionId!)}>Continue your challenge</Button>
            : <Button block onClick={() => { trackAction("daily_challenge_start_clicked", { sceneKey: data.sceneKey }); navigate("/ispy/challenge"); }}><CameraIcon size={20} />Take a photo &amp; join</Button>}
        {resumeError ? <p role="alert">{resumeError}</p> : null}
        {result ? <p className="daily-challenge__result"><TrophyIcon size={18} />{result}</p> : null}
      </div>
      <div className="daily-challenge__board">
        <div className="daily-challenge__board-head">
          <h3>Today’s community board</h3>
          <span>{data.participantCount} finished</span>
        </div>
        {data.words.length ? <>
          <ol className="daily-challenge__words">{data.words.slice(0, BOARD_ROWS).map(word => <li key={word.label} className={word.foundByYou ? "is-yours" : undefined}>
            <span className="daily-challenge__bar" style={{ width: `${wordShare(word, data.words)}%` }} aria-hidden="true" />
            <strong>{word.label}</strong>
            {word.foundByYou ? <span className="daily-challenge__mine"><CheckIcon size={14} />Yours</span> : null}
            <span className="daily-challenge__count">{word.count}<span className="visually-hidden"> {word.count === 1 ? "learner" : "learners"}</span></span>
          </li>)}</ol>
          {hidden > 0 ? <p className="daily-challenge__more">+{hidden} more {hidden === 1 ? "word" : "words"} found today</p> : null}
        </> : <div className="daily-challenge__empty"><p><strong>Be the first to add a word!</strong> Every word you keep shows up here for everyone.</p></div>}
      </div>
    </div>
  </section>;
}
