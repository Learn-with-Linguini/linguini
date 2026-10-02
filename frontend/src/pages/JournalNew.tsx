import { LoadingScreen } from "../components/LoadingScreen";
import { ErrorState } from "../components/ErrorState";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Button, Feedback } from "../components/ui";
import { ChevronRightIcon } from "../components/icons";
import { ImageUpload } from "../components/ImageUpload";
import { MediaImage } from "../components/MediaImage";
import { useAppState } from "../state/useAppState";
import { getJournalContext } from "../lib/api";
import type { JournalPhotoOption } from "../lib/api";
import { queryError, queryKeys } from "../lib/queryKeys";
import { useQuery } from "@tanstack/react-query";
import type { JournalEntry } from "../data/types";

export function JournalNew() {
  const { date } = useParams<{ date?: string }>();
  const { data, isPending: loading, error: queryErrorValue } = useQuery({
    queryKey: queryKeys.journalDayContext(date ?? "today"),
    queryFn: ({ signal }) => getJournalContext(date, signal),
  });
  const error = queryError(queryErrorValue);
  if (loading) return <LoadingScreen label="Loading journal…" />;
  if (error || !data) return <ErrorState title="We couldn't open your journal" message={error ?? "Your journal isn't available right now."} retry={() => window.location.reload()} backTo="/journal" />;
  return <JournalForm key={data.entry?.id ?? `new-${data.date}`} entry={data.entry} date={data.date} photoOptions={data.photoOptions} wordSuggestions={data.wordSuggestions} />;
}

export function JournalForm({ entry, date, photoOptions, wordSuggestions, onSaved }: { entry: JournalEntry | null; date: string; photoOptions: JournalPhotoOption[]; wordSuggestions: string[]; onSaved?: (entry: JournalEntry) => void }) {
  const navigate = useNavigate();
  const { saveJournalEntry, journalSaving, journalSaveError, learner, activeProfile } = useAppState();
  const shownDate = new Date(`${date}T12:00:00`);
  const isToday = date === new Date().toLocaleDateString("en-CA");
  const [title, setTitle] = useState(entry?.title ?? "");
  const [body, setBody] = useState(entry?.body ?? "");
  const [photos, setPhotos] = useState(entry?.photos ?? []);
  const [uploading, setUploading] = useState(false);
  const [selectedWords, setSelectedWords] = useState<string[]>(entry?.wordsUsed ?? []);
  const [photoPickerOpen, setPhotoPickerOpen] = useState(photos.length === 0 && photoOptions.length > 0);

  const toggleWord = (word: string) =>
    setSelectedWords((current) =>
      current.includes(word) ? current.filter((item) => item !== word) : [...current, word],
    );

  const save = async () => {
    if (journalSaving || uploading || !body.trim() || (!entry && !activeProfile)) return;
    const saved = await saveJournalEntry({
      title: title.trim() || "Today's entry",
      mediaAssetId: photos[0]?.mediaAssetId ?? null,
      photoAssetIds: photos.map(photo => photo.mediaAssetId),
      body: body.trim(),
      wordsUsed: selectedWords,
    }, entry?.id, date);
    if (saved) {
      if (onSaved) onSaved(saved);
      else navigate(`/journal/${saved.id}`);
    }
  };

  return (
    <div className="journal-editor">
      <header className="journal-editor__header">
        <span className="journal-editor__date">{shownDate.toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "short" })}</span>
        <h1>{entry ? "Edit entry" : isToday ? "Today's entry" : "Journal entry"}</h1>
      </header>

      <div className="journal-editor__layout">
        <section className="journal-editor__write">
          <label className="visually-hidden" htmlFor="entry-title">Title</label>
          <input
            id="entry-title"
            disabled={journalSaving}
            maxLength={200}
            className="journal-editor__title-input"
            placeholder="Give today a title"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
          />
          <label className="visually-hidden" htmlFor="entry-body">Your entry</label>
          <textarea
            id="entry-body"
            disabled={journalSaving}
            maxLength={20000}
            className="journal-editor__body-input"
            placeholder="Start writing…"
            value={body}
            onChange={(event) => setBody(event.target.value)}
          />
          <div className="journal-editor__write-foot">
            <span className="small muted">{body.trim() ? body.trim().split(/\s+/).length : 0} words</span>
          </div>
          {selectedWords.length ? (
            <Feedback>
              <div className="stack-2">
                <strong>Nice picks</strong>
                <span className="small muted">
                  Try using {selectedWords.slice(0, 2).join(" and ")} in one sentence.
                </span>
              </div>
            </Feedback>
          ) : null}
        </section>

        <aside className="journal-editor__aside">
          <section className="journal-editor__panel">
            <h2 className="journal-editor__panel-title">Photos</h2>
            {photos.length ? (
              <div className="photo-strip" aria-label={`${photos.length} photos added`}>
                {photos.map((photo, index) => <div key={photo.mediaAssetId} className="photo-thumb">
                  <MediaImage assetId={photo.mediaAssetId} title={`Journal photo ${index + 1}`} width={320} lazy />
                  <button type="button" className="photo-thumb__remove" aria-label={`Remove photo ${index + 1}`}
                    disabled={journalSaving || uploading}
                    onClick={() => setPhotos(current => current.filter(item => item.mediaAssetId !== photo.mediaAssetId))}>
                    &times;
                  </button>
                </div>)}
              </div>
            ) : null}
            <div className="journal-editor__upload">
              <ImageUpload cameraEnabled={learner.cameraOn} disabled={journalSaving} onBusyChange={setUploading}
                dropzoneLabel={photos.length ? "Add another photo" : "Add a few photos from your day"}
                onUploaded={(image) => setPhotos(current => current.some(photo => photo.mediaAssetId === image.id) ? current
                  : [...current, { mediaAssetId: image.id, imageUrl: image.signedUrl, displayOrder: current.length }])} />
            </div>
            {photoOptions.length ? (
              <>
                <button
                  type="button"
                  className="journal-editor__disclosure"
                  aria-expanded={photoPickerOpen}
                  onClick={() => setPhotoPickerOpen(v => !v)}
                >
                  Choose from this day's practice photos <ChevronRightIcon size={18} />
                </button>
                {photoPickerOpen ? (
                  <div className="journal-editor__scene-grid">
                    {photoOptions.map((option) => {
                      const selected = photos.some(photo => photo.mediaAssetId === option.mediaAssetId);
                      return <button key={option.mediaAssetId} type="button" disabled={uploading || journalSaving}
                        className={`scene-pick${selected ? " scene-pick--selected" : ""}`} aria-pressed={selected}
                        onClick={() => setPhotos(current => selected
                          ? current.filter(photo => photo.mediaAssetId !== option.mediaAssetId)
                          : [...current, { mediaAssetId: option.mediaAssetId, imageUrl: option.imageUrl, displayOrder: current.length }])}>
                        <MediaImage assetId={option.mediaAssetId} title="Photo from your practice session" width={320} lazy />
                      </button>;
                    })}
                  </div>
                ) : null}
              </>
            ) : <p className="small muted">No photos from completed sessions on this day. Add from your camera or gallery above.</p>}
          </section>

          <section className="journal-editor__panel">
            <h2 className="journal-editor__panel-title">Words from today</h2>
            <div className="chip-row">
              {!wordSuggestions.length ? <p className="small muted">No translated words were added from your photos today</p> : null}
              {wordSuggestions.map((word) => (
                <button
                  key={word}
                  type="button"
                  className={`chip${selectedWords.includes(word) ? " chip--selected" : ""}`}
                  aria-pressed={selectedWords.includes(word)}
                  disabled={journalSaving}
                  onClick={() => toggleWord(word)}
                >
                  {word}
                </button>
              ))}
            </div>
          </section>
        </aside>
      </div>

      <div className="journal-editor__actions">
        {journalSaveError ? <p role="alert">{journalSaveError}</p> : null}
        {journalSaving ? <p role="status">Saving journal…</p> : null}
        {!entry && !activeProfile ? <p role="alert">Choose a language in Profile before saving.</p> : null}
        <Button block className="journal-editor__save" disabled={journalSaving || uploading || !body.trim() || (!entry && !activeProfile)} onClick={save}>
          Save entry
        </Button>
      </div>
    </div>
  );
}
