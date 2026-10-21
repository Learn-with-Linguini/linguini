import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button, Card, IconButton } from "../components/ui";
import { ChevronLeftIcon, ChevronRightIcon, PlusIcon } from "../components/icons";
import { JournalPhotoMosaic } from "../components/JournalPhotoMosaic";
import { LoadingScreen } from "../components/LoadingScreen";
import { ErrorState } from "../components/ErrorState";
import { useJournalsQuery } from "../state/queries";
import type { JournalEntry } from "../data/types";

function formatDate(date: string) {
  return new Date(`${date}T12:00:00`).toLocaleDateString("en-GB", {
    weekday: "long",
    day: "numeric",
    month: "long",
  });
}

function monthStart(date: Date) {
  return new Date(date.getFullYear(), date.getMonth(), 1);
}

function dateFromEntry(date: string) {
  const [year, month] = date.split("-").map(Number);
  return new Date(year, month - 1, 1);
}

function monthLabel(date: Date) {
  return date.toLocaleDateString("en-GB", { month: "long", year: "numeric" });
}

function isInMonth(date: string, month: Date) {
  const entryMonth = dateFromEntry(date);
  return entryMonth.getFullYear() === month.getFullYear() && entryMonth.getMonth() === month.getMonth();
}

function wordCount(text: string) {
  const count = text.trim().split(/\s+/).filter(Boolean).length;
  return `${count} ${count === 1 ? "word" : "words"}`;
}

export function Journal() {
  const { journal, journalLoading, journalError } = useJournalsQuery();
  if (journalLoading) return <LoadingScreen label="Loading journal history..." />;
  if (journalError) return <ErrorState title="We couldn't load your journal" message={journalError} retry={() => window.location.reload()} />;
  return <JournalMonths journal={journal} />;
}

function JournalMonths({ journal }: { journal: JournalEntry[] }) {
  const navigate = useNavigate();
  const [visibleMonth, setVisibleMonth] = useState(() =>
    monthStart(journal.length ? dateFromEntry(journal[0].date) : new Date()),
  );
  const visibleEntries = journal.filter((entry) => isInMonth(entry.date, visibleMonth));

  const changeMonth = (offset: number) => {
    setVisibleMonth((current) => new Date(current.getFullYear(), current.getMonth() + offset, 1));
  };

  return (
    <div className="journal-page">
      <header className="journal-page__header">
        <div className="month-switcher">
          <IconButton label="Previous month" onClick={() => changeMonth(-1)}>
            <ChevronLeftIcon />
          </IconButton>
          <h1>{monthLabel(visibleMonth)}</h1>
          <IconButton label="Next month" onClick={() => changeMonth(1)}>
            <ChevronRightIcon />
          </IconButton>
        </div>
        <Button className="journal-page__add" onClick={() => navigate("/journal/new")}>
          <PlusIcon size={18} /> New entry
        </Button>
      </header>

      <div className="field">
        <label className="field__label" htmlFor="journal-missed-day">
          Add an entry for another day
        </label>
        <input
          id="journal-missed-day"
          type="date"
          className="input"
          max={new Date().toLocaleDateString("en-CA")}
          onChange={(event) => {
            if (event.target.value) navigate(`/journal/new/${event.target.value}`);
          }}
        />
      </div>

      {visibleEntries.length === 0 ? (
        <Card>
          <div className="journal-empty">
            <strong>Nothing written in {monthLabel(visibleMonth)}</strong>
            <p className="small muted">A few sentences a day goes a long way.</p>
          </div>
        </Card>
      ) : (
        <div className="journal-feed">
          {visibleEntries.map((entry) => (
            <button
              key={entry.id}
              type="button"
              className="journal-card"
              onClick={() => navigate(`/journal/${entry.id}`)}
            >
              <JournalPhotoMosaic photos={entry.photos} title={entry.title} />
              <span className="journal-card__body">
                <h2>{entry.title}</h2>
                {entry.body.trim() ? <span className="journal-card__excerpt">{entry.body}</span> : null}
                <span className="journal-card__footer">
                  <span className="journal-card__date">{formatDate(entry.date)}</span>
                  <span className="journal-card__words">{wordCount(entry.body)}</span>
                </span>
              </span>
            </button>
          ))}
        </div>
      )}

      <button
        type="button"
        className="journal-fab"
        aria-label="New journal entry"
        onClick={() => navigate("/journal/new")}
      >
        <PlusIcon size={24} />
      </button>
    </div>
  );
}
