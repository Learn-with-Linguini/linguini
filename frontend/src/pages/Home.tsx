import { useState } from "react";
import type { CSSProperties } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Card } from "../components/ui";
import { BookIcon, CameraIcon, ChevronRightIcon, JournalIcon } from "../components/icons";
import { MediaImage } from "../components/MediaImage";
import { getActivePractice } from "../lib/api";
import { sessionDestination } from "../lib/sessionRoute";
import { friendlyError, queryError, queryKeys } from "../lib/queryKeys";
import { useAppState } from "../state/useAppState";
import { useVocabularyQuery } from "../state/queries";
import type { VocabRecord } from "../data/types";

function greeting() {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

function dayLabel(date: string) {
  return new Intl.DateTimeFormat(undefined, { weekday: "short" }).format(new Date(`${date}T12:00:00`));
}

function localDateKey(value: Date | string) {
  const parsed = typeof value === "string" ? new Date(value) : value;
  return `${parsed.getFullYear()}-${String(parsed.getMonth() + 1).padStart(2, "0")}-${String(parsed.getDate()).padStart(2, "0")}`;
}

function lastSevenDates() {
  const today = new Date();
  return Array.from({ length: 7 }, (_, index) => {
    const day = new Date(today.getFullYear(), today.getMonth(), today.getDate() - (6 - index));
    return localDateKey(day);
  });
}

function TaskProgressRing({ completed, total }: { completed: number; total: number }) {
  const percentage = total === 0 ? 0 : Math.min(100, Math.round((completed / total) * 100));
  return (
    <div className="home-task-progress">
      <div
        className="home-task-progress__ring"
        style={{ "--home-progress": `${percentage * 3.6}deg` } as CSSProperties}
        role="img"
        aria-label={`${completed} of ${total} tasks complete`}
      >
        <strong aria-hidden="true">{percentage}%</strong>
      </div>
      <span className="home-task-progress__caption">{completed} of {total} tasks</span>
    </div>
  );
}

function WordsLearntChart({ dates, vocabulary, loading, error }: { dates: string[]; vocabulary: VocabRecord[]; loading: boolean; error: string | null }) {
  const counts = dates.map(date => vocabulary.filter(word => word.firstLearnedAt && localDateKey(word.firstLearnedAt) === date).length);
  const peak = Math.max(...counts);
  const total = counts.reduce((sum, count) => sum + count, 0);
  return (
    <section className="home-words" aria-labelledby="home-words-title">
      <div className="home-words__heading">
        <div><h2 id="home-words-title">Words learnt each day</h2><p>The last seven days of new words.</p></div>
        <strong>{total} this week</strong>
      </div>
      {loading ? <p role="status">Loading your words…</p> : error ? null : (
        <>
          <ol className="home-words__chart" aria-label="New words learnt on each of the last seven days">
            {dates.map((date, index) => (
              <li
                key={date}
                role="img"
                aria-label={`${counts[index]} ${counts[index] === 1 ? "word" : "words"} on ${dayLabel(date)}`}
                className={`home-words__bar${counts[index] === 0 ? " home-words__bar--empty" : ""}${index === dates.length - 1 ? " home-words__bar--today" : ""}`}
              >
                <span className="home-words__track">
                  <span className="home-words__fill" style={{ "--home-bar": `${peak === 0 ? 0 : Math.round((counts[index] / peak) * 100)}%` } as CSSProperties}>
                    <span className="home-words__value" aria-hidden="true">{counts[index]}</span>
                  </span>
                </span>
                <span className="home-words__day" aria-hidden="true">{dayLabel(date)}</span>
              </li>
            ))}
          </ol>
          {total === 0 ? <p className="home-words__empty">Learn a word today to start your chart.</p> : null}
        </>
      )}
    </section>
  );
}

export function Home() {
  const navigate = useNavigate();
  const { learner, activeProfile, progress, progressLoading, progressError } = useAppState();
  const { vocabulary, vocabularyLoading, vocabularyError } = useVocabularyQuery();
  const queryClient = useQueryClient();
  const profileId = activeProfile?.id ?? "";
  const { data: resume, error: resumeQueryError, isPending: resumeLoading } = useQuery({
    queryKey: queryKeys.activeSession(profileId),
    queryFn: () => getActivePractice(),
  });
  const resumeError = queryError(resumeQueryError);
  const [continueError, setContinueError] = useState<string | null>(null);
  const streak = progress?.streak;
  const activeDays = streak?.days.filter(day => day.active).length ?? 0;
  const streakCaption = streak
    ? activeDays === streak.days.length
      ? "Perfect week!"
      : streak.days[streak.days.length - 1]?.active
        ? "Keep it going!"
        : "Check in today"
    : "";

  const continuePractice = async () => {
    setContinueError(null);
    try {
      const fresh = await queryClient.fetchQuery({
        queryKey: queryKeys.activeSession(profileId),
        queryFn: () => getActivePractice(),
        staleTime: 0,
      });
      if (!fresh) {
        queryClient.setQueryData(queryKeys.activeSession(profileId), null);
        return;
      }
      navigate(sessionDestination(fresh).path);
    } catch (reason) {
      setContinueError(friendlyError(reason));
    }
  };

  return (
    <div className="home stack">
      <header className="home-greeting">
        <img src="/linguini-logo.png" width={64} height={64} alt="" />
        <div>
          <h1>{greeting()}, {learner.name || "friend"}!</h1>
        </div>
      </header>

      <section className="home-streak" aria-label="Your seven day learning streak">
        <div className="home-streak__heading">
          <h2>Your {streak?.days.length ?? 7}-day streak</h2>
          <strong className="home-streak__xp">{progressLoading || progressError ? "--" : progress?.xp ?? 0} XP</strong>
        </div>
        {progressLoading ? <p role="status">Loading your streak…</p> : progressError ? null : (
          <div className="home-streak__body">
            <ol className="home-streak__week">
              {streak?.days.map((day, index) => (
                <li key={day.date} className={`home-streak__day${day.active ? " home-streak__day--checked" : ""}${index === streak.days.length - 1 ? " home-streak__day--today" : ""}`}>
                  <img className="home-streak__farfalle" src="/pasta-assets/farfalle.png" alt="" />
                  <span>{dayLabel(day.date)}</span>
                </li>
              ))}
            </ol>
            <div className="home-streak__count">
              <strong>{activeDays}<span> / {streak?.days.length ?? 7}</span></strong>
              <span className="home-streak__caption">{streakCaption}</span>
            </div>
          </div>
        )}
      </section>

      <section className="home-plan" aria-label="Today's plan">
        {progressLoading || resumeLoading ? <p role="status">Loading your practice...</p> : progressError || resumeError ? (
          <p role="alert">{progressError ?? resumeError} Reload to retry.</p>
        ) : resume ? (
          <Card className="home-featured home-featured--resume">
            <div className="home-featured__image">
              <MediaImage assetId={resume.session.sceneMediaAssetId} title={resume.title} />
            </div>
            <div className="home-featured__body">
              <h3>{resume.title}</h3>
              {resume.progress.totalTaskCount > 0 ? <TaskProgressRing completed={resume.progress.completedTaskCount} total={resume.progress.totalTaskCount} /> : null}
              {continueError ? <p role="alert">{continueError}</p> : null}
              <Button block onClick={() => void continuePractice()}>
                Continue learning <ChevronRightIcon size={20} />
              </Button>
            </div>
          </Card>
        ) : (
          <Card className="home-featured home-featured--new">
            <div className="home-featured__body">
              <h3>Turn a place into a lesson</h3>
              <p className="home-featured__description">Choose a photo or one of our ready-made scenes.</p>
              <Button block onClick={() => navigate("/practice")}>
                Begin a new practice <ChevronRightIcon size={20} />
              </Button>
            </div>
          </Card>
        )}
      </section>

      <section className="home-tiles" aria-labelledby="home-tiles-title">
        <h2 id="home-tiles-title">More ways to learn</h2>
        <div className="home-tiles__grid">
          <Button variant="quiet" className="home-tile" onClick={() => navigate("/practice")}>
            <CameraIcon size={28} />
            <span>Capture a scene</span>
          </Button>
          <Button variant="quiet" className="home-tile" onClick={() => navigate("/journal")}>
            <JournalIcon size={28} />
            <span>My journal</span>
          </Button>
          <Button variant="quiet" className="home-tile" onClick={() => navigate("/vocabulary")}>
            <BookIcon size={28} />
            <span>Review words</span>
          </Button>
        </div>
      </section>

      <WordsLearntChart
        dates={streak?.days.map(day => day.date) ?? lastSevenDates()}
        vocabulary={vocabulary}
        loading={vocabularyLoading}
        error={vocabularyError}
      />
    </div>
  );
}
