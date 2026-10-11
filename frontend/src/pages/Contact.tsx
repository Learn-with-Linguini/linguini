import { useState, type ChangeEvent, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";
import { Button, Card, Feedback } from "../components/ui";
import { submitPublicSupportRequest, submitSupportRequest, type SupportAttachmentInput, type SupportIssueType } from "../lib/api";
import { useAuth } from "../state/Auth";
import { LoadingScreen } from "../components/LoadingScreen";

const topics = {
  general: "General feedback",
  technical: "Something is not working",
  content: "Incorrect lesson content",
  account: "Account or privacy question",
} as const;

const allowedAttachmentTypes = new Set<SupportAttachmentInput["mimeType"]>([
  "image/jpeg", "image/png", "image/webp", "application/pdf", "text/plain",
]);

const maxAttachmentBytes = 5 * 1024 * 1024;
const maxTotalAttachmentBytes = 10 * 1024 * 1024;

const toBase64 = (file: File) => new Promise<string>((resolve, reject) => {
  const reader = new FileReader();
  reader.onerror = () => reject(new Error("We could not read one of your attachments."));
  reader.onload = () => resolve(String(reader.result).split(",", 2)[1] ?? "");
  reader.readAsDataURL(file);
});

export function Contact() {
  const { session, loading: authLoading } = useAuth();
  const [searchParams] = useSearchParams();
  const initialType = searchParams.get("type");
  const [topic, setTopic] = useState<SupportIssueType>(initialType && initialType in topics ? initialType as SupportIssueType : "general");
  const [email, setEmail] = useState("");
  const [subject, setSubject] = useState(searchParams.get("subject") ?? "");
  const [details, setDetails] = useState(searchParams.get("description") ?? "");
  const [attachments, setAttachments] = useState<File[]>([]);
  const [attachmentError, setAttachmentError] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [sent, setSent] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const chooseAttachments = (event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? []);
    setAttachmentError(null);
    if (files.length > 3) {
      setAttachments([]);
      setAttachmentError("Attach up to three files.");
      return;
    }
    if (files.some(file => !allowedAttachmentTypes.has(file.type as SupportAttachmentInput["mimeType"]))) {
      setAttachments([]);
      setAttachmentError("Attach only JPEG, PNG, WebP, PDF, or text files.");
      return;
    }
    if (files.some(file => !file.size || file.size > maxAttachmentBytes)) {
      setAttachments([]);
      setAttachmentError("Each attachment must be between 1 byte and 5 MB.");
      return;
    }
    if (files.reduce((total, file) => total + file.size, 0) > maxTotalAttachmentBytes) {
      setAttachments([]);
      setAttachmentError("Attachments must total 10 MB or less.");
      return;
    }
    setAttachments(files);
  };

  const send = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (submitting) return;
    const form = event.currentTarget;
    setSubmitError(null);
    setSent(false);
    setSubmitting(true);
    try {
      const encodedAttachments = await Promise.all(attachments.map(async file => ({
        fileName: file.name,
        mimeType: file.type as SupportAttachmentInput["mimeType"],
        dataBase64: await toBase64(file),
      })));
      const request = {
        subject: subject.trim(),
        description: details.trim(),
        issueType: topic,
        attachments: encodedAttachments,
      };
      if (session) await submitSupportRequest(request);
      else await submitPublicSupportRequest({ ...request, email: email.trim() });
      setSent(true);
      setSubject("");
      setDetails("");
      setAttachments([]);
      form.reset();
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : "We could not send your request. Please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  if (authLoading) return <LoadingScreen label="Preparing support…" />;

  return (
    <div className="stack contact-page">
      <div>
        <h1>Contact us</h1>
        <p className="muted">Linguini is in beta. Tell us what is confusing, broken, or worth improving.</p>
      </div>

      <Card plain className="contact-card">
        <form className="stack" onSubmit={send}>
          {!session ? <div className="field">
            <label className="field__label" htmlFor="feedback-email">Your email address</label>
            <input id="feedback-email" className="input" type="email" autoComplete="email" required maxLength={320} value={email} onChange={event => setEmail(event.target.value)} />
            <span className="small muted">We will only use this to reply to your request.</span>
          </div> : <p className="panel-note small">We’ll use the email address associated with your Linguini account so our team can reply.</p>}

          <div className="field">
            <label className="field__label" htmlFor="feedback-topic">What can we help with?</label>
            <select
              id="feedback-topic"
              className="input"
              value={topic}
              onChange={event => setTopic(event.target.value as SupportIssueType)}
            >
              {Object.entries(topics).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </div>

          <div className="field">
            <label className="field__label" htmlFor="feedback-subject">Subject</label>
            <input id="feedback-subject" className="input" required minLength={3} maxLength={160} value={subject} onChange={event => setSubject(event.target.value)} />
          </div>

          <div className="field">
            <label className="field__label" htmlFor="feedback-details">Your feedback</label>
            <textarea
              id="feedback-details"
              className="textarea"
              value={details}
              required
              minLength={10}
              maxLength={4000}
              placeholder="Include what you were trying to do and what you expected to happen."
              onChange={event => setDetails(event.target.value)}
            />
            <span className="small muted">Please do not include passwords, API keys, or other sensitive information.</span>
          </div>

          <div className="field">
            <label className="field__label" htmlFor="feedback-attachments">Attachments <span className="muted">(optional)</span></label>
            <input
              id="feedback-attachments"
              className="input contact-file-input"
              type="file"
              multiple
              accept="image/jpeg,image/png,image/webp,application/pdf,text/plain"
              onChange={chooseAttachments}
            />
            <span className="small muted">Up to three JPEG, PNG, WebP, PDF, or text files; 5 MB each and 10 MB total.</span>
            {attachments.length ? <ul className="contact-attachment-list">{attachments.map(file => <li key={`${file.name}-${file.lastModified}`}>{file.name}</li>)}</ul> : null}
            {attachmentError ? <p role="alert" className="contact-error">{attachmentError}</p> : null}
          </div>

          <Button block type="submit" disabled={submitting || !!attachmentError || (!session && !email.trim()) || subject.trim().length < 3 || details.trim().length < 10}>
            {submitting ? "Sending…" : "Submit request"}
          </Button>
          {sent ? <Feedback tone="good"><p role="status">Thanks — your request was sent to Linguini Support. We’ll reply to {session ? "the email address on your account" : email.trim()}.</p></Feedback> : null}
          {submitError ? <Feedback tone="warn"><p role="alert">{submitError}</p></Feedback> : null}
        </form>
      </Card>

      <aside className="profile-ai-note">
        <strong>Reporting a lesson answer?</strong>
        <p>Use “Report this answer” after an exercise. Linguini will include the prompt, your answer, and the displayed solution so we can investigate it faster.</p>
      </aside>

      <p className="contact-page__direct small muted">Your request is sent directly to the Linguini support team.</p>
    </div>
  );
}
