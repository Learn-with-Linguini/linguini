import { Link } from "react-router-dom";
import { Button } from "./ui";

type ErrorNoticeProps = {
  message: string;
  title?: string;
  compact?: boolean;
  retry?: () => void;
  retryLabel?: string;
};

/** Friendly recovery copy for inline actions and full-page data failures. */
export function ErrorNotice({
  message,
  title = "Something went wrong",
  compact = false,
  retry,
  retryLabel = "Try again",
}: ErrorNoticeProps) {
  return (
    <section className={`error-notice${compact ? " error-notice--compact" : ""}`} role="alert">
      <span className="error-notice__icon" aria-hidden="true">!</span>
      <div className="error-notice__copy">
        <strong>{title}</strong>
        <p>{message}</p>
      </div>
      {retry ? <Button variant="secondary" onClick={retry}>{retryLabel}</Button> : null}
    </section>
  );
}

export function ErrorState({
  message,
  title = "We hit a small bump",
  retry,
  backTo,
  backLabel = "Go back",
}: ErrorNoticeProps & { backTo?: string; backLabel?: string }) {
  return (
    <div className="error-state">
      <ErrorNotice title={title} message={message} />
      <div className="error-state__actions">
        {retry ? <Button onClick={retry}>Try again</Button> : null}
        {backTo ? <Link className="btn btn--secondary" to={backTo}>{backLabel}</Link> : null}
      </div>
    </div>
  );
}
