import { LoadingScreen } from "../components/LoadingScreen";
import { ErrorState } from "../components/ErrorState";
import { useNavigate, useParams } from "react-router-dom";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { getJournal, getJournalContext } from "../lib/api";
import { queryError, queryKeys } from "../lib/queryKeys";
import type { JournalEntry } from "../data/types";
import { JournalForm } from "./JournalNew";
import { Button, IconButton, TopBar } from "../components/ui";
import { ChevronLeftIcon, ChevronRightIcon } from "../components/icons";
import { MediaImage } from "../components/MediaImage";
import { useAppState } from "../state/useAppState";
import { useVocabularyQuery } from "../state/queries";

function wordCount(text: string) {
  const count = text.trim().split(/\s+/).filter(Boolean).length;
  return `${count} ${count === 1 ? "word" : "words"}`;
}

export function JournalEntryPage() {
  const { entryId } = useParams();
  return <JournalEntryDetail key={entryId} entryId={entryId ?? ""} />;
}

function JournalEntryDetail({ entryId }: { entryId: string }) {
  const navigate = useNavigate();
  const { activeProfile } = useAppState();
  const { vocabulary } = useVocabularyQuery();
  const queryClient = useQueryClient();
  const { data: entry, isPending: loading, error: queryErrorValue } = useQuery({
    queryKey: queryKeys.journal(entryId),
    queryFn: ({ signal }) => getJournal(entryId, signal),
  });
  const error = queryError(queryErrorValue);
  const [editing, setEditing] = useState(false);
  const [activePhotoIndex, setActivePhotoIndex] = useState(0);
  if (loading) return <LoadingScreen label="Loading journal entry…" />;
  if (error) return <ErrorState title="We couldn't open this entry" message={error} retry={() => window.location.reload()} backTo="/journal" />;

  if (!entry) {
    return (
      <div className="stack">
        <TopBar title="Entry not found" />
        <p className="muted">That entry is no longer here.</p>
      </div>
    );
  }

  const linked = entry.languageProfileId === activeProfile?.id
    ? vocabulary.filter((record) => entry.wordsUsed.includes(record.word)) : [];
  if (editing) return <JournalEntryEditor key={entry.id} entry={entry} onSaved={(saved) => { queryClient.setQueryData(queryKeys.journal(entryId), saved); setEditing(false); }} />;
  const photoIndex = Math.min(activePhotoIndex, entry.photos.length - 1);
  const photo = entry.photos[photoIndex];
  const changePhoto = (offset: number) => setActivePhotoIndex((photoIndex + offset + entry.photos.length) % entry.photos.length);

  const formattedDate = new Date(`${entry.date}T12:00:00`).toLocaleDateString("en-GB", {
    weekday: "long",
    day: "numeric",
    month: "short",
  });

  return (
    <div className="journal-entry">
      <header className="journal-entry__header">
        <span className="journal-entry__date">{formattedDate}</span>
        <h1 className="journal-entry__title">{entry.title}</h1>
        <div className="journal-entry__meta">
          <span>{wordCount(entry.body)}</span>
          {entry.photos.length ? (
            <span>{entry.photos.length} {entry.photos.length === 1 ? "photo" : "photos"}</span>
          ) : null}
        </div>
        <Button variant="secondary" className="journal-entry__edit" onClick={() => setEditing(true)}>
          Edit entry
        </Button>
      </header>

      {photo ? (
        <div className="journal-entry__gallery">
          <div className="journal-carousel">
            <div className="scene">
              <MediaImage key={photo.mediaAssetId} assetId={photo.mediaAssetId} title={entry.title} />
            </div>
            {entry.photos.length > 1 ? <>
              <IconButton className="journal-carousel__control journal-carousel__control--previous" label="Previous photo" onClick={() => changePhoto(-1)}><ChevronLeftIcon /></IconButton>
              <IconButton className="journal-carousel__control journal-carousel__control--next" label="Next photo" onClick={() => changePhoto(1)}><ChevronRightIcon /></IconButton>
              <span className="journal-carousel__count" aria-live="polite">{photoIndex + 1} of {entry.photos.length}</span>
            </> : null}
          </div>
          {entry.photos.length > 1 ? (
            <div className="journal-entry__thumbs">
              {entry.photos.map((p, i) => (
                <button
                  key={p.mediaAssetId}
                  type="button"
                  className={`journal-entry__thumb${i === photoIndex ? " is-active" : ""}`}
                  aria-label={`Show photo ${i + 1}`}
                  aria-current={i === photoIndex}
                  onClick={() => setActivePhotoIndex(i)}
                >
                  <MediaImage assetId={p.mediaAssetId} title={`Photo ${i + 1}`} width={320} lazy />
                </button>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}

      <article className="journal-entry__body">
        {entry.body.split(/\n{2,}/).map((para, i) => <p key={i}>{para}</p>)}
      </article>

      {linked.length ? (
        <section className="journal-entry__vocab">
          <h2>From your vocabulary</h2>
          <div className="list">
            {linked.map((record) => (
              <div key={record.id} className="list__row" style={{ cursor: "default" }}>
                <div className="grow">
                  <strong>{record.word}</strong>
                  <p className="small muted">{record.translation}</p>
                </div>
                <span className={`pill pill--${record.status}`}>{record.status}</span>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      <Button variant="secondary" className="journal-entry__back" onClick={() => navigate("/journal")}>
        Back to journal
      </Button>
    </div>
  );
}

function JournalEntryEditor({ entry, onSaved }: { entry: JournalEntry; onSaved: (entry: JournalEntry) => void }) {
  const { data, isPending: loading, error: queryErrorValue } = useQuery({
    queryKey: queryKeys.journalDayContext(entry.date),
    queryFn: ({ signal }) => getJournalContext(entry.date, signal),
  });
  const error = queryError(queryErrorValue);
  if (loading) return <LoadingScreen label="Loading journal…" />;
  if (error || !data) return <ErrorState title="We couldn't open your journal" message={error ?? "Your journal isn't available right now."} retry={() => window.location.reload()} backTo="/journal" />;
  return <JournalForm entry={entry} date={entry.date} photoOptions={data.photoOptions} wordSuggestions={data.wordSuggestions} onSaved={onSaved} />;
}
