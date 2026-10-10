import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { submitLessonReport, type LessonReportIssue } from "../lib/api";
import { Button, Feedback, IconButton } from "./ui";
import { CloseIcon } from "./icons";

const issueOptions: Array<{ value: LessonReportIssue; label: string }> = [
  { value: "answer_marked_incorrectly", label: "My answer was marked incorrectly" },
  { value: "solution_incorrect", label: "The displayed solution is incorrect" },
  { value: "wording_unclear", label: "The wording or translation is unclear" },
  { value: "audio_incorrect", label: "The audio or pronunciation is incorrect" },
  { value: "other", label: "Something else" },
];

export function ReportIssueLink({
  reportType,
  fields,
  label = "Report this answer",
}: {
  reportType: string;
  fields: Array<[label: string, value: string | null | undefined]>;
  label?: string;
}) {
  const [open, setOpen] = useState(false);
  const [issue, setIssue] = useState<LessonReportIssue | null>(null);
  const [details, setDetails] = useState("");
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const titleId = useId();
  const modalRef = useRef<HTMLElement>(null);

  useEffect(() => {
    if (!open) return;
    modalRef.current?.querySelector<HTMLButtonElement>("button")?.focus();
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !sending) setOpen(false);
    };
    document.addEventListener("keydown", closeOnEscape);
    return () => document.removeEventListener("keydown", closeOnEscape);
  }, [open, sending]);

  const close = () => {
    if (sending) return;
    setOpen(false);
    setIssue(null);
    setDetails("");
    setSent(false);
    setError(null);
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!issue || sending) return;
    setSending(true);
    setError(null);
    try {
      await submitLessonReport({
        reportType,
        issue,
        additionalDetails: details.trim(),
        context: fields
          .filter((field): field is [string, string] => Boolean(field[1]))
          .map(([fieldLabel, value]) => ({ label: fieldLabel, value })),
      });
      setSent(true);
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "We could not send your report. Please try again.");
    } finally {
      setSending(false);
    }
  };

  return (
    <>
      <button type="button" className="report-issue-link" aria-haspopup="dialog" aria-expanded={open} onClick={() => setOpen(true)}>
        {label}
      </button>
      {open ? <div className="report-modal__backdrop" onMouseDown={close}>
        <section ref={modalRef} className="report-modal" role="dialog" aria-modal="true" aria-labelledby={titleId} onMouseDown={event => event.stopPropagation()}>
          <div className="report-modal__header">
            <div><h2 id={titleId}>Report this lesson</h2><p>What seems wrong?</p></div>
            <IconButton label="Close report" disabled={sending} onClick={close}><CloseIcon /></IconButton>
          </div>
          {sent ? <div className="stack">
            <Feedback tone="good"><p role="status"><strong>Report sent.</strong> Thanks for helping us improve this lesson.</p></Feedback>
            <Button block onClick={close}>Done</Button>
          </div> : <form className="stack" onSubmit={submit}>
            <div className="report-modal__issues" role="radiogroup" aria-label="Issue with this lesson">
              {issueOptions.map(option => <button
                key={option.value}
                type="button"
                role="radio"
                aria-checked={issue === option.value}
                className={`report-modal__issue${issue === option.value ? " report-modal__issue--selected" : ""}`}
                onClick={() => setIssue(option.value)}
              >{option.label}</button>)}
            </div>
            <div className="field">
              <label className="field__label" htmlFor={`${titleId}-details`}>Additional details <span className="muted">(optional)</span></label>
              <textarea id={`${titleId}-details`} className="input report-modal__details" maxLength={2000} value={details} onChange={event => setDetails(event.target.value)} placeholder="Tell us what you expected to see." />
            </div>
            {error ? <p className="contact-error" role="alert">{error}</p> : null}
            <Button block disabled={!issue || sending} type="submit">{sending ? "Sending…" : "Send report"}</Button>
          </form>}
        </section>
      </div> : null}
    </>
  );
}
