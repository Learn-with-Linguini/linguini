import { useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { InlineLoader } from "../components/LoadingScreen";
import { MediaImage } from "../components/MediaImage";
import { BasilIcon, BookIcon, ChevronRightIcon, EyeIcon, PlayIcon, TrophyIcon } from "../components/icons";
import { Button } from "../components/ui";
import { getActivePractice } from "../lib/api";
import { sessionDestination } from "../lib/sessionRoute";
import { friendlyError, queryError, queryKeys } from "../lib/queryKeys";
import { useAppState } from "../state/useAppState";
import { useVocabularyQuery } from "../state/queries";
import { WalkthroughCoachmark } from "../components/WalkthroughCoachmark";
import { FIRST_LESSON_WALKTHROUGH_VERSION, needsFirstLessonWalkthrough } from "../lib/walkthrough";
import { learningProgress } from "../lib/practiceTasks";
import { useChefStandings, useGamification } from "../state/gamification";
import { trackAction } from "../lib/analytics.ts";
import { homeRevisitPhotos } from "../lib/homeRevisit";

function greeting() {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

function dayLabel(date: string) {
  return new Intl.DateTimeFormat(undefined, { weekday: "narrow" }).format(new Date(`${date}T12:00:00`));
}

function localDateKey(value: Date | string) {
  const parsed = typeof value === "string" ? new Date(value) : value;
  return `${parsed.getFullYear()}-${String(parsed.getMonth() + 1).padStart(2, "0")}-${String(parsed.getDate()).padStart(2, "0")}`;
}

function PastaStreak({ days }: { days: { date: string; active: boolean }[] }) {
  return <section className="home-streak" aria-labelledby="home-streak-title">
    <div className="home-streak__copy"><h2 id="home-streak-title">Your pasta streak</h2></div>
    <ol className="home-streak__week" aria-label="Your activity over the last seven days">
      {days.map((day, index) => <li key={day.date} className={`${day.active ? "is-active" : ""}${index === days.length - 1 ? " is-today" : ""}`}>
        <span className="home-streak__day-label">{dayLabel(day.date)}</span>
        <span className="home-streak__loop" aria-label={`${day.active ? "Practised" : "No practice"} on ${day.date}`}>
          <img src="/pasta-assets/streak-loop.png" alt="" />
          {index === days.length - 1 ? <BasilIcon className="home-streak__leaf" /> : null}
        </span>
      </li>)}
    </ol>
  </section>;
}

export function Home() {
  const basil = useGamification();
  const standings = useChefStandings();
  const navigate = useNavigate();
  const { learner, user, activeProfile, progress, progressLoading, progressError, profileSaving, saveUser } = useAppState();
  const { vocabulary, vocabularyLoading, vocabularyError } = useVocabularyQuery();
  const queryClient = useQueryClient();
  const profileId = activeProfile?.id ?? "";
  const { data: resume, error: resumeQueryError, isPending: resumeLoading } = useQuery({ queryKey: queryKeys.activeSession(profileId), queryFn: () => getActivePractice() });
  const resumeError = queryError(resumeQueryError);
  const [continueError, setContinueError] = useState<string | null>(null);
  const [walkthroughDismissed, setWalkthroughDismissed] = useState(false);
  const [walkthroughError, setWalkthroughError] = useState<string | null>(null);
  const beginPracticeRef = useRef<HTMLDivElement>(null);
  const exploreRailRef = useRef<HTMLDivElement>(null);

  const weekDates = new Set(progress?.streak.days.map(day => day.date) ?? []);
  const wordsThisWeek = vocabulary.filter(word => word.firstLearnedAt && weekDates.has(localDateKey(word.firstLearnedAt))).length;
  const exploredScenes = progress?.scenarios.filter(scene => scene.status !== "in-progress").length ?? 0;
  const leaderboardPosition = standings.data?.currentRank;
  const revisitScenes = useMemo(() => homeRevisitPhotos(progress?.scenarios ?? [], vocabulary), [progress, vocabulary]);
  const revisitLoading = progressLoading || vocabularyLoading;
  const revisitError = progressError || vocabularyError;
  const { completed, total } = resume ? learningProgress(resume.tasks) : { completed: 0, total: 0 };
  const percent = total > 0 ? Math.min(100, Math.round((completed / total) * 100)) : 0;

  const continuePractice = async () => {
    setContinueError(null);
    try {
      const fresh = await queryClient.fetchQuery({ queryKey: queryKeys.activeSession(profileId), queryFn: () => getActivePractice(), staleTime: 0 });
      if (!fresh) { queryClient.setQueryData(queryKeys.activeSession(profileId), null); navigate("/practice"); return; }
      navigate(sessionDestination(fresh).path);
    } catch (reason) { setContinueError(friendlyError(reason)); }
  };

  const finishWalkthrough = async () => {
    setWalkthroughError(null);
    const saved = await saveUser({ walkthroughVersionSeen: FIRST_LESSON_WALKTHROUGH_VERSION });
    if (saved) setWalkthroughDismissed(true);
    else setWalkthroughError("We couldn't save this choice. Please try again.");
  };

  const walkthroughOpen = !walkthroughDismissed && !progressLoading && !progressError && !resumeLoading && !resumeError && !resume
    && Boolean(user?.onboardingCompleted) && needsFirstLessonWalkthrough(user?.walkthroughVersionSeen);

  return <div className="home-dashboard">
    <header className="home-welcome">
      <div><h2>{greeting()}, {learner.name || "friend"}</h2><p>Ready to cook?</p></div>
      <span className="home-points" aria-label={basil.isPending ? "Loading your Basil total" : basil.isError ? "Basil total unavailable" : `${basil.data?.basil.lifetime ?? 0} total Basil`}><BasilIcon />{basil.isPending || basil.isError ? "—" : basil.data?.basil.lifetime ?? 0} Basil</span>
    </header>

    <div className="home-dashboard__grid">
      <main className="home-dashboard__main">
        <section className={`home-next-step${resume ? " home-next-step--resume" : " home-next-step--new"}`} aria-labelledby="home-next-title">
          <div className="home-next-step__image" aria-hidden="true">{resume ? <MediaImage assetId={resume.session.sceneMediaAssetId} title={resume.title} width={1280} /> : <img src="/photos/cafe-interior.jpg" alt="" />}</div>
          <div className="home-next-step__overlay" />
          <div className="home-next-step__content">
            <span className="home-eyebrow">Your next step</span>
            <h2 id="home-next-title">{resume ? `Continue ${resume.title}` : "Turn a place into a lesson"}</h2>
            <p>{resume ? `${completed} of ${total} activities complete` : "Choose a photo or one of our ready-made scenes."}</p>
            {resume && total > 0 ? <div className="home-next-step__progress-row"><div className="home-next-step__progress" role="progressbar" aria-label="Practice progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent}><span style={{ width: `${percent}%` }} /></div><strong>{percent}%</strong></div> : null}
            {continueError ? <p className="home-next-step__error" role="alert">{continueError}</p> : null}
            <div ref={beginPracticeRef}><Button onClick={() => {
              if (resume) {
                trackAction("home_continue_practice_clicked", { sessionId: resume.session.id });
                void continuePractice();
              } else {
                trackAction("home_begin_practice_clicked");
                navigate("/practice");
              }
            }}><PlayIcon size={21} /> {resume ? "Continue practice" : "Begin a new practice"}</Button></div>
          </div>
        </section>

        <section className="home-explore" aria-labelledby="home-explore-title">
          <div className="home-section-heading"><h2 id="home-explore-title">Continue exploring</h2></div>
          <div className="home-explore__rail-wrap">
            <div ref={exploreRailRef} className="home-explore__rail">
              {revisitLoading ? <div className="home-explore-card home-revisit-state" role="status"><InlineLoader compact label="Loading revisit photos…" /></div> : revisitError ?
                <div className="home-explore-card home-revisit-state"><p role="alert">We couldn’t load your revisit photos.</p><Button variant="quiet" onClick={() => {
                  trackAction("home_revisit_retried");
                  void queryClient.invalidateQueries({ queryKey: queryKeys.progress(profileId) });
                  void queryClient.invalidateQueries({ queryKey: queryKeys.vocabulary(profileId) });
                }}>Retry revisit photos</Button></div> : revisitScenes.length ? revisitScenes.map((scene, index) =>
                <button key={scene.mediaAssetId} className="home-explore-card home-explore-card--revisit" type="button" aria-label={`Revisit words from ${scene.title}`} onClick={() => {
                  trackAction("home_explore_vocabulary_clicked", { source: "photo", position: index + 1 });
                  navigate(`/practice/sessions/${encodeURIComponent(scene.sessionId)}/review`);
                }}>
                  <div className="home-explore-card__image"><MediaImage assetId={scene.mediaAssetId} title={scene.title} width={640} lazy /></div>
                  <div className="home-explore-card__body"><span className="home-tag home-tag--revisit"><BookIcon size={14} /> Revisit</span><strong>{scene.title}</strong><span>{scene.wordCount} {scene.wordCount === 1 ? "word" : "words"} to practise</span></div>
                </button>) : <button className="home-explore-card" type="button" onClick={() => { trackAction("home_explore_vocabulary_clicked", { source: "all_words" }); navigate("/vocabulary"); }}>
                  <div className="home-explore-card__image home-revisit-empty" aria-hidden="true"><BookIcon size={48} /></div>
                  <div className="home-explore-card__body"><span className="home-tag home-tag--revisit"><BookIcon size={14} /> Revisit</span><strong>Your vocabulary</strong><span>{vocabulary.length ? "Review the words you've found" : "Your completed photo lessons will appear here"}</span></div>
                </button>}
              <button className="home-explore-card" type="button" onClick={() => { trackAction("home_explore_ispy_clicked"); navigate("/ispy"); }}>
                <div className="home-explore-card__image"><img src="/scenes/grocery-store.jpg" alt="A colourful grocery store scene" /></div>
                <div className="home-explore-card__body"><span className="home-tag home-tag--play"><EyeIcon size={14} /> Quick play</span><strong>I-Spy challenge</strong><span>Test what you can spot</span></div>
              </button>
            </div>
            <button className="home-explore__next" type="button" aria-label="Show the next activity" onClick={() => {
              const rail = exploreRailRef.current;
              if (!rail) return;
              const atEnd = rail.scrollLeft + rail.clientWidth >= rail.scrollWidth - 4;
              rail.scrollTo({ left: atEnd ? 0 : rail.scrollLeft + rail.clientWidth * 0.82,
                behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
            }}><ChevronRightIcon /></button>
          </div>
        </section>
      </main>

      <aside className="home-dashboard__aside">
        {progressLoading ? <div className="home-dashboard__loading"><InlineLoader label="Loading your progress…" /></div> : progressError ? <p className="home-dashboard__error" role="alert">{progressError}</p> : <PastaStreak days={progress?.streak.days ?? []} />}
        <section className="home-progress-card" aria-labelledby="home-progress-title">
          <div className="home-section-heading home-section-heading--compact"><div><span className="home-progress-card__eyebrow">This week</span><h2 id="home-progress-title">Your progress</h2></div></div>
          {vocabularyLoading ? <InlineLoader compact label="Loading your words…" /> : vocabularyError ? <p role="alert">{vocabularyError}</p> : <div className="home-progress-card__stats"><div><span className="home-stat-icon home-stat-icon--words"><BookIcon /></span><strong>{wordsThisWeek}</strong><span>words</span></div><div><span className="home-stat-icon home-stat-icon--scenes"><EyeIcon /></span><strong>{exploredScenes}</strong><span>scenes</span></div></div>}
        </section>
        {user?.id ? <button className="home-league" type="button" aria-busy={standings.isPending} onClick={() => { trackAction("home_chef_standings_clicked"); navigate("/ispy"); }}><span className="home-league__badge" aria-hidden="true"><TrophyIcon size={26} /></span><span><strong>Chefs of the Day</strong><small>{standings.isPending ? "Loading your standing…" : standings.isError ? "Your standing is unavailable." : leaderboardPosition ? `Your current standing: #${leaderboardPosition}` : "Earn Basil to join today’s board."}</small></span><ChevronRightIcon /></button> : null}
      </aside>
    </div>

    {walkthroughOpen ? <WalkthroughCoachmark targetRef={beginPracticeRef} step={1} totalSteps={3} title="Start with the world around you" description="Linguini turns a photo or one of our ready-made scenes into a speaking lesson." nextLabel="Show me" saving={profileSaving} error={walkthroughError} onNext={() => navigate("/practice")} onSkip={() => void finishWalkthrough()} /> : null}
  </div>;
}
