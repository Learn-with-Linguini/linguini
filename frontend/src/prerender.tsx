import { StrictMode } from "react";
import { renderToString } from "react-dom/server";
import { StaticRouter } from "react-router-dom";
import { SiteRoot } from "./SiteRoot";
import MarketingApp from "./marketing/MarketingApp";

export { marketingRoutes, learnerRoutePatterns } from "./marketing/routes";
export { movedPosts } from "./marketing/data/posts";

export function renderPage(path: string): string {
  return renderToString(
    <StrictMode>
      <StaticRouter location={path}>
        <SiteRoot><MarketingApp /></SiteRoot>
      </StaticRouter>
    </StrictMode>,
  );
}
