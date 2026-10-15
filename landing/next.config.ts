import { existsSync, readdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import type { NextConfig } from "next";
import { movedPosts } from "./data/posts";

const publicAppPath = path.join(path.dirname(fileURLToPath(import.meta.url)), "public", "app");
const publicAppIndexPath = path.join(publicAppPath, "index.html");

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  // Dev only: lets local browser previews served from 127.0.0.1 load dev scripts and hot reload.
  allowedDevOrigins: ["127.0.0.1"],
  async redirects() {
    // Once a custom domain is live, list the old hosts (e.g. "linguini-landing.vercel.app") in
    // REDIRECT_FROM_HOSTS so links and rankings earned on them move to NEXT_PUBLIC_SITE_URL.
    const canonical = process.env.NEXT_PUBLIC_SITE_URL?.replace(/\/$/, "");
    const oldHosts = canonical ? (process.env.REDIRECT_FROM_HOSTS ?? "").split(",").map(h => h.trim()).filter(Boolean) : [];
    return [
      ...Object.entries(movedPosts).map(([from, to]) => ({
        source: `/blog/${from}`,
        destination: `/blog/${to}`,
        permanent: true,
      })),
      ...oldHosts.map(host => ({
        source: "/:path*",
        has: [{ type: "host" as const, value: host }],
        destination: `${canonical}/:path*`,
        permanent: true,
      })),
    ];
  },
  async rewrites() {
    if (!existsSync(publicAppIndexPath)) return { fallback: [] };

    const appAssetRewrites = readdirSync(publicAppPath, { withFileTypes: true })
      .filter(entry => entry.name !== "index.html" && entry.name !== "assets")
      .flatMap(entry => {
        if (entry.isDirectory()) {
          return [{
            source: `/${entry.name}/:path*`,
            destination: `/app/${entry.name}/:path*`,
          }];
        }
        if (entry.isFile()) {
          return [{
            source: `/${entry.name}`,
            destination: `/app/${entry.name}`,
          }];
        }
        return [];
      });

    return {
      fallback: [
        ...appAssetRewrites,
        { source: "/:path*", destination: "/app/index.html" },
      ],
    };
  },
  async headers() {
    return [
      {
        source: "/app/assets/:path*",
        headers: [
          { key: "Cache-Control", value: "public, max-age=31536000, immutable" },
        ],
      },
    ];
  },
  images: {
    formats: ["image/avif", "image/webp"],
  },
  outputFileTracingIncludes: {
    "/og": ["./assets/**/*", "./public/photos/**/*", "./public/brand/**/*", "./public/pasta/**/*"],
    "/opengraph-image": ["./assets/**/*", "./public/photos/**/*", "./public/brand/**/*", "./public/pasta/**/*"],
    "/blog/*/*-image": ["./assets/**/*", "./public/photos/**/*", "./public/brand/**/*", "./public/pasta/**/*"],
  },
};

export default nextConfig;
