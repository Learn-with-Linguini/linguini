import { StrictMode, Suspense, lazy } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { AnalyticsTracker } from "./components/AnalyticsTracker.tsx";
import { isMarketingPath } from "./marketing/paths";

const LearnerRoot = lazy(() => import("./LearnerRoot"));
const MarketingApp = lazy(() => import("./marketing/MarketingApp"));
const Root = isMarketingPath(window.location.pathname) ? MarketingApp : LearnerRoot;

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <AnalyticsTracker />
      <Suspense fallback={null}>
        <Root />
      </Suspense>
    </BrowserRouter>
  </StrictMode>,
);
