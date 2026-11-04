import { readFile, stat } from "node:fs/promises";
import { resolve, sep } from "node:path";
import type { Plugin } from "vite";
import { marketingRoutes, learnerRoutePatterns } from "../src/marketing/routes.js";
import { movedPosts } from "../src/marketing/data/posts.js";

function matcher(source: string): RegExp {
  return new RegExp(`^${source.replace(/:[a-zA-Z]+\(([^)]+)\)|:[a-zA-Z]+\*|:[a-zA-Z]+/g, (token, options: string | undefined) => options ? `(?:${options})` : token.endsWith("*") ? ".*" : "[^/]+")}$`);
}

/** Preview mirrors Vercel routing instead of silently serving Home for every URL. */
export function previewRoutes(): Plugin {
  return {
    name: "linguini-preview-routes",
    configurePreviewServer(server) {
      const output = resolve(server.config.root, server.config.build.outDir);
      const learner = learnerRoutePatterns.map(matcher);
      server.middlewares.use(async (request, response, next) => {
        if (request.method !== "GET" && request.method !== "HEAD") return next();
        const url = new URL(request.url ?? "/", "http://localhost");
        const path = url.pathname;
        const moved = movedPosts[path.replace(/^\/blog\//, "")];
        if (path.startsWith("/blog/") && moved) {
          response.writeHead(308, { Location: `/blog/${moved}${url.search}` });
          return response.end();
        }
        if (path !== "/" && path.endsWith("/")) {
          response.writeHead(308, { Location: `${path.replace(/\/+$/, "")}${url.search}` });
          return response.end();
        }
        const direct = resolve(output, `.${path}`);
        if (direct.startsWith(`${output}${sep}`)) {
          const file = await stat(direct).catch(() => null);
          if (file?.isFile()) {
            if (path.endsWith(".html")) {
              response.writeHead(308, { Location: `${path.slice(0, -5) === "/index" ? "/" : path.slice(0, -5)}${url.search}` });
              return response.end();
            }
            return next();
          }
        }
        const publicPage = marketingRoutes.includes(path);
        const app = learner.some(pattern => pattern.test(path));
        const shell = ["/app", "/share", "/404"].includes(path);
        const file = publicPage ? path === "/" ? "index" : path.slice(1) : app ? "app" : shell ? path.slice(1) : "404";
        try {
          const html = await readFile(resolve(output, `${file}.html`));
          response.statusCode = publicPage || app || shell ? 200 : 404;
          response.setHeader("Content-Type", "text/html; charset=utf-8");
          if (!publicPage) response.setHeader("X-Robots-Tag", "noindex, follow");
          response.end(request.method === "HEAD" ? undefined : html);
        } catch (error) { next(error); }
      });
    },
  };
}
