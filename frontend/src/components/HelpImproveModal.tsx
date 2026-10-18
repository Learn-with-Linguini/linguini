import { useEffect, useState, type FormEvent } from "react";
import { Button, IconButton } from "./ui";
import { CloseIcon } from "./icons";
import { submitSurvey } from "../lib/api";

const ratings = [
  { value: 1, label: "Angry", src: "/ratings/rating-1.png", desc: "1 star — very unhappy" },
  { value: 2, label: "Sad", src: "/ratings/rating-2.png", desc: "2 stars — disappointed" },
  { value: 3, label: "Neutral", src: "/ratings/rating-3.png", desc: "3 stars — okay" },
  { value: 4, label: "Happy", src: "/ratings/rating-4.png", desc: "4 stars — good" },
  { value: 5, label: "Loved it", src: "/ratings/rating-5.png", desc: "5 stars — loved it" },
];

interface HelpImproveModalProps {
  open: boolean;
  onClose: () => void;
  triggerSource?: string;
  lessonCount?: number | null;
}

export function HelpImproveModal({
  open,
  onClose,
  triggerSource = "profile",
  lessonCount = null,
}: HelpImproveModalProps) {
  const [rating, setRating] = useState<number | null>(null);
  const [usageFrequency, setUsageFrequency] = useState("");
  const [motivation, setMotivation] = useState("");
  const [improvements, setImprovements] = useState("");
  const [receiveFollowUp, setReceiveFollowUp] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) {
      setRating(null);
      setUsageFrequency("");
      setMotivation("");
      setImprovements("");
      setReceiveFollowUp(false);
      setSubmitting(false);
      setSubmitted(false);
      setError(null);
      return;
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !submitting) {
        onClose();
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [open, onClose, submitting]);

  if (!open) return null;

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!rating) {
      setError("Please select a rating to share your feedback.");
      return;
    }

    setSubmitting(true);
    setError(null);
    try {
      await submitSurvey({
        rating,
        usageFrequency: usageFrequency.trim(),
        motivation: motivation.trim(),
        improvements: improvements.trim(),
        receiveFollowUp,
        triggerSource,
        lessonCount,
      });
      setSubmitted(true);
      setTimeout(() => {
        onClose();
      }, 2400);
    } catch {
      setError("We couldn't save your feedback right now. Please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      className="survey-backdrop"
      role="dialog"
      aria-modal="true"
      aria-labelledby="survey-title"
      onMouseDown={e => {
        if (e.target === e.currentTarget && !submitting) onClose();
      }}
    >
      <div className="survey-sheet" onMouseDown={e => e.stopPropagation()}>
        <div className="survey-sheet__drag-bar" aria-hidden="true" />

        <div className="survey-sheet__header">
          <div className="survey-sheet__title">
            <h2 id="survey-title">Help us improve</h2>
            <p>Tell us how your learning is going so we can make Linguini better.</p>
          </div>
          <IconButton label="Close feedback" disabled={submitting} onClick={onClose}>
            <CloseIcon />
          </IconButton>
        </div>

        {submitted ? (
          <div className="survey-success-state">
            <img src="/ratings/rating-5.png" alt="Happy Linguini mascot" />
            <h3>Thank you for your feedback!</h3>
            <p className="muted">Your thoughts help us shape lessons and improve the app.</p>
            <Button block onClick={onClose}>
              Done
            </Button>
          </div>
        ) : (
          <form className="survey-questions" onSubmit={event => void handleSubmit(event)}>
            <div className="survey-rating-section">
              <strong>How would you rate your experience on Linguini?</strong>
              <div className="survey-rating-options" role="radiogroup" aria-label="Experience rating">
                {ratings.map(option => (
                  <button
                    key={option.value}
                    type="button"
                    role="radio"
                    aria-checked={rating === option.value}
                    aria-label={option.desc}
                    className={`survey-rating-btn${rating === option.value ? " is-selected" : ""}`}
                    onClick={() => {
                      setRating(option.value);
                      setError(null);
                    }}
                  >
                    <img src={option.src} alt={option.label} />
                    <span>{option.label}</span>
                  </button>
                ))}
              </div>
            </div>

            <div className="survey-question">
              <label htmlFor="survey-freq">1. How often will you use Linguini?</label>
              <input
                id="survey-freq"
                className="input"
                type="text"
                value={usageFrequency}
                onChange={e => setUsageFrequency(e.target.value)}
                placeholder="e.g. Daily, a few times a week, during commutes…"
              />
            </div>

            <div className="survey-question">
              <label htmlFor="survey-motivation">2. What is the motivation to use Linguini?</label>
              <input
                id="survey-motivation"
                className="input"
                type="text"
                value={motivation}
                onChange={e => setMotivation(e.target.value)}
                placeholder="e.g. Trip to Spain, talking with family, daily practice…"
              />
            </div>

            <div className="survey-question">
              <label htmlFor="survey-improvements">3. What would you like to see improved the most?</label>
              <textarea
                id="survey-improvements"
                className="input textarea"
                rows={3}
                value={improvements}
                onChange={e => setImprovements(e.target.value)}
                placeholder="Share any suggestions, missing features, or confusing parts…"
              />
            </div>

            <label className="survey-checkbox">
              <input
                type="checkbox"
                checked={receiveFollowUp}
                onChange={e => setReceiveFollowUp(e.target.checked)}
              />
              <span>Receive follow-up to your feedback</span>
            </label>

            {error ? <p role="alert">{error}</p> : null}

            <Button type="submit" block disabled={submitting || !rating}>
              {submitting ? "Submitting feedback…" : "Send feedback"}
            </Button>
          </form>
        )}
      </div>
    </div>
  );
}
