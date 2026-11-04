import { StrictMode, lazy } from "react";
import { createRoot, hydrateRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { SiteRoot } from "./SiteRoot";
import { isMarketingPath } from "./marketing/paths";

const LearnerRoot = lazy(() => import("./LearnerRoot"));
const MarketingApp = lazy(() => import("./marketing/MarketingApp"));
const container = document.getElementById("root")!;
const Root = container.dataset.page === "not-found" || isMarketingPath(window.location.pathname) ? MarketingApp : LearnerRoot;

const tree = (
  <StrictMode>
    <BrowserRouter>
      <SiteRoot><Root /></SiteRoot>
    </BrowserRouter>
  </StrictMode>
);

if (container.dataset.prerendered === "true") {
  hydrateRoot(container, tree);
} else {
  // The query-dependent share page supplies its own metadata after mounting.
  if (isMarketingPath(window.location.pathname)) {
    document.head.querySelectorAll("[data-shell-meta]").forEach(node => node.remove());
  }
  createRoot(container).render(tree);
}
