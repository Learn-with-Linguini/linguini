import type { MetadataRoute } from "next";
import { site } from "@/lib/site";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: site.title,
    short_name: site.shortTitle,
    description: site.description,
    start_url: "/",
    scope: "/",
    display: "standalone",
    background_color: "#fbf8ef",
    theme_color: "#fbf8ef",
    lang: "en",
    categories: ["education"],
    icons: [
      { src: "/icon.png", sizes: "64x64", type: "image/png" },
      { src: "/apple-icon.png", sizes: "180x180", type: "image/png", purpose: "any" },
      { src: "/brand/linguini-logo.png", sizes: "360x360", type: "image/png", purpose: "any" },
    ],
  };
}
