import type { NextConfig } from "next";
import { movedPosts } from "./data/posts";

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
