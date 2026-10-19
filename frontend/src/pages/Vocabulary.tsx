import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button, Card, IconButton, Tabs } from "../components/ui";
import { BookIcon, CameraIcon, CloseIcon, FilterIcon, PlayIcon, SpeakerIcon } from "../components/icons";
import { SceneVisual } from "../components/SceneVisual";
import { InlineLoader, LoadingScreen } from "../components/LoadingScreen";
import { ErrorState } from "../components/ErrorState";
import type { VocabStatus, WordClass } from "../data/types";
import { mediaImageUrl } from "../lib/api";
import { groupVocabularyByPhoto, vocabularyCategories, vocabularyLabel } from "../lib/vocabularyGroups";
import { speak } from "../lib/speech";
import { trackAction } from "../lib/analytics.ts";
import { useAppState } from "../state/useAppState";
import { useScenesQuery, useVocabularyQuery } from "../state/queries";

type StatusFilter = VocabStatus | "all";
const statusLabels: { id: StatusFilter; label: string }[] = [
  { id: "all", label: "All" }, { id: "new", label: "New" },
  { id: "learning", label: "Learning" }, { id: "mastered", label: "Mastered" },
];

export function Vocabulary() {
  const navigate = useNavigate();
  const { learner, progress } = useAppState();
  const { vocabulary, vocabularyLoading, vocabularyError } = useVocabularyQuery();
  const { scenes, scenesLoading, scenesError } = useScenesQuery();
  const [view, setView] = useState<"journey" | "list">("journey");
  const [status, setStatus] = useState<StatusFilter>("all");
  const [wordClass, setWordClass] = useState<WordClass | "all">("all");
  const [category, setCategory] = useState("all");
  const [showFilters, setShowFilters] = useState(false);
  const [draftWordClass, setDraftWordClass] = useState<WordClass | "all">("all");
  const [draftCategory, setDraftCategory] = useState("all");
  const filterSheetRef = useRef<HTMLDivElement>(null);
  const wordClasses: (WordClass | "all")[] = ["all", ...new Set(vocabulary.map((item) => item.wordClass))];
  const categories = useMemo(() => ["all", ...new Set(vocabulary.flatMap((item) => vocabularyCategories(item, scenes)))], [vocabulary, scenes]);
  const rows = vocabulary.filter((item) => (status === "all" || item.status === status)
    && (wordClass === "all" || item.wordClass === wordClass)
    && (category === "all" || vocabularyCategories(item, scenes).includes(category)));
  const sceneGroups = useMemo(() => groupVocabularyByPhoto(vocabulary, scenes, (id) => mediaImageUrl(id, 640)).sceneGroups, [vocabulary, scenes]);
  const scenarioByAsset = useMemo(() => new Map(progress?.scenarios.map((scenario) => [scenario.mediaAssetId, scenario]) ?? []), [progress]);

  const openFilters = () => { setDraftWordClass(wordClass); setDraftCategory(category); setShowFilters(true); };
  const closeFilters = () => setShowFilters(false);
  const applyFilters = () => {
    trackAction("vocabulary_filters_applied", { wordClass: draftWordClass, category: draftCategory });
    setWordClass(draftWordClass);
    setCategory(draftCategory);
    closeFilters();
  };

  useEffect(() => {
    if (!showFilters) return;
    const previousFocus = document.activeElement as HTMLElement | null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    filterSheetRef.current?.querySelector<HTMLButtonElement>("button")?.focus();
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") closeFilters();
      if (event.key !== "Tab") return;
      const buttons = filterSheetRef.current?.querySelectorAll<HTMLButtonElement>("button:not(:disabled)");
      const first = buttons?.[0]; const last = buttons?.[buttons.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => { document.body.style.overflow = previousOverflow; document.removeEventListener("keydown", handleKeyDown); previousFocus?.focus(); };
  }, [showFilters]);

  if (vocabularyLoading) return <LoadingScreen label="Loading your journey..." />;
  if (vocabularyError) return <ErrorState title="We couldn't load your journey" message={vocabularyError} retry={() => window.location.reload()} />;

  return <div className="stack vocabulary-page revisit-page">
    <header className="vocabulary-page__header">
      <div><h1>Revisit</h1><p className="muted">Come back to the places and words you’ve learned.</p></div>
      <Button variant="secondary" className="vocabulary-page__view-toggle" aria-pressed={view === "list"} onClick={() => {
        const nextView = view === "journey" ? "list" : "journey";
        trackAction("vocabulary_view_toggled", { view: nextView });
        setView(nextView);
      }}>
        <span className="vocabulary-page__view-icon" aria-hidden="true">
          {view === "journey" ? <BookIcon size={22} /> : <CameraIcon size={22} />}
        </span>
        <span>{view === "journey" ? "Vocabulary List" : "Scenes"}</span>
      </Button>
    </header>

    {view === "journey" ? <div className="revisit-scenes">
      {scenesLoading ? <InlineLoader label="Loading places…" /> : null}
      {scenesError ? <p role="alert">{scenesError} Your saved words are still available.</p> : null}
      {!vocabulary.length ? <Card><div className="stack-2"><h2>Your journey starts with a scene</h2><p>Practise with a photo and the places you explore will appear here.</p><Button onClick={() => navigate("/practice")}>Start a practice</Button></div></Card> : null}
      {sceneGroups.map(({ scene, words }, index) => {
        const scenario = scenarioByAsset.get(scene.id);
        const startsSecondColumn = index === Math.ceil(sceneGroups.length / 2);
        return <section key={scene.id} className={`revisit-stop${startsSecondColumn ? " revisit-stop--column-start" : ""}`}>
          <div className="revisit-stop__card">
            <div className="revisit-stop__image">
              <SceneVisual scene={scene} className="vocabulary-scene__image" lazy />
              <span className="revisit-stop__word-count">
                {words.length} {words.length === 1 ? "word" : "words"}
              </span>
              <Button className="revisit-stop__action" disabled={!scenario?.sessionId}
                aria-label={scenario?.sessionId ? `Revisit ${scene.title}` : `Revisit unavailable for ${scene.title}`}
                onClick={() => scenario?.sessionId && navigate(`/practice/sessions/${scenario.sessionId}/learn`)}>
                <PlayIcon size={18} /> {scenario?.sessionId ? "Revisit" : "Unavailable"}
              </Button>
            </div>
            <div className="vocabulary-scene__content stack-2">
              <div className="vocabulary-scene__heading"><h2>{scene.title}</h2></div>
              <div className="vocabulary-scene__words">{words.map((item) => {
                const spokenWord = vocabularyLabel(item);
                return <div key={item.id} className="vocabulary-scene__word">
                  <span><strong>{spokenWord}</strong><small>{item.translation}</small></span><IconButton label={`Hear ${spokenWord}`} onClick={() => { trackAction("vocabulary_audio_played", { word: spokenWord }); speak(spokenWord, learner.languageCode); }}><SpeakerIcon size={18} /></IconButton>
                </div>;
              })}</div>
            </div>
          </div>
        </section>;
      })}
    </div> : <>
      <div className="spread vocabulary-page__list-controls"><Tabs options={statusLabels} value={status} onChange={setStatus} /><IconButton label="Filters" aria-haspopup="dialog" aria-expanded={showFilters} onClick={openFilters}><FilterIcon /></IconButton></div>
      {showFilters ? <div className="vocabulary-filter-backdrop" onMouseDown={(event) => event.target === event.currentTarget && closeFilters()}><div ref={filterSheetRef} className="vocabulary-filter-sheet" role="dialog" aria-modal="true" aria-labelledby="revisit-filter-title">
        <span className="vocabulary-filter-sheet__handle" aria-hidden="true" /><div className="vocabulary-filter-sheet__header"><h2 id="revisit-filter-title">Filter words</h2><IconButton label="Close filters" onClick={closeFilters}><CloseIcon /></IconButton></div>
        <FilterGroup label="Word type" options={wordClasses} value={draftWordClass} onChange={setDraftWordClass} /><FilterGroup label="Place" options={categories} value={draftCategory} onChange={setDraftCategory} /><Button block className="vocabulary-filter-sheet__apply" onClick={applyFilters}>Apply filters</Button>
      </div></div> : null}
      <div className="list vocabulary-list">{rows.map((item) => {
        const spokenWord = vocabularyLabel(item);
        return <article key={item.id} className="list__row vocabulary-card"><div className="grow vocabulary-card__content">
          <div className="vocabulary-card__heading"><strong className="vocabulary-card__title">{spokenWord}</strong><p className="vocabulary-card__translation">{item.translation}</p></div>{item.phoneticText ? <p className="small muted" aria-label="Pronunciation">{item.phoneticText}</p> : null}
          <div className="vocabulary-card__footer"><div className="vocabulary-card__tags"><span className="pill pill--new">{item.wordClass}</span>{vocabularyCategories(item, scenes).map((title) => <span key={title} className="pill pill--new">{title}</span>)}</div><IconButton className="vocabulary-card__audio" label={`Hear ${spokenWord}`} onClick={() => { trackAction("vocabulary_audio_played", { word: spokenWord }); speak(spokenWord, learner.languageCode); }}><SpeakerIcon size={18} /></IconButton></div>
        </div></article>;
      })}</div>{!rows.length ? <Card><p className="small">No words match these filters yet.</p></Card> : null}
    </>}
  </div>;
}

function FilterGroup<T extends string>({ label, options, value, onChange }: { label: string; options: T[]; value: T; onChange: (value: T) => void }) {
  return <fieldset className="vocabulary-filter-group"><legend>{label}</legend><div className="chip-row">{options.map((option) => <button key={option} type="button" className={`chip${option === value ? " chip--selected" : ""}`} aria-pressed={option === value} onClick={() => onChange(option)}>{option}</button>)}</div></fieldset>;
}
