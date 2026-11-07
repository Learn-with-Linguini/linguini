import { JSDOM } from "jsdom";

export function parseSitemap(source) {
  const { document } = new JSDOM(source, { contentType: "application/xml" }).window;
  if (document.documentElement.localName !== "urlset" ||
      document.documentElement.namespaceURI !== "http://www.sitemaps.org/schemas/sitemap/0.9") {
    throw new Error("Expected an XML sitemap, not an HTML fallback");
  }
  const urls = [...document.querySelectorAll("url > loc")].map(node => new URL(node.textContent));
  if (!urls.length || new Set(urls.map(url => url.href)).size !== urls.length) {
    throw new Error("Sitemap must contain a nonempty, unique URL list");
  }
  const origin = urls[0].origin;
  for (const url of urls) {
    if (!/^https?:$/.test(url.protocol) || url.origin !== origin || url.username || url.password || url.search || url.hash ||
        (url.pathname !== "/" && url.pathname.endsWith("/"))) {
      throw new Error(`Noncanonical sitemap URL: ${url.href}`);
    }
  }
  return urls;
}

export function inspectPage(source, url, { indexable = true } = {}) {
  const { document } = new JSDOM(source).window;
  const problems = [];
  const exactlyOne = selector => {
    const nodes = document.head.querySelectorAll(selector);
    if (nodes.length !== 1) problems.push(`expected one ${selector}, found ${nodes.length}`);
    return nodes[0];
  };
  const meta = (name, property = false) => exactlyOne(`meta[${property ? "property" : "name"}="${name}"]`)?.content ?? "";
  const title = exactlyOne("title")?.textContent.trim() ?? "";
  if (!title) problems.push("empty title");
  const description = indexable ? meta("description") : document.head.querySelector('meta[name="description"]')?.content ?? "";
  if (indexable && description.length < 40) problems.push("missing or very short description");
  const robots = meta("robots");
  if (indexable) {
    if (!/(?:^|,)\s*index\s*(?:,|$)/.test(robots) || /noindex/i.test(robots)) problems.push(`unexpected robots: ${robots}`);
    const canonical = exactlyOne('link[rel="canonical"]')?.href;
    if (canonical !== url.href) problems.push(`canonical ${canonical ?? "missing"} differs from ${url.href}`);
    if (meta("og:url", true) !== url.href) problems.push("og:url differs from canonical");
    for (const [name, property] of [["og:title", true], ["og:description", true], ["og:type", true], ["og:image:alt", true],
      ["twitter:title", false], ["twitter:description", false], ["twitter:image:alt", false]]) {
      if (!meta(name, property)) problems.push(`empty ${name}`);
    }
    if (meta("twitter:card") !== "summary_large_image") problems.push("missing large Twitter card");
    const image = meta("og:image", true);
    if (meta("twitter:image") !== image) problems.push("sharing images disagree");
    try {
      const parsed = new URL(image);
      if (!/^https?:$/.test(parsed.protocol)) throw new Error();
    } catch { problems.push("og:image must be an absolute HTTP(S) URL"); }
    if (document.querySelectorAll("h1").length !== 1) problems.push("expected one server-rendered h1");
    if ((document.querySelector("#root")?.textContent.trim().length ?? 0) < 200) problems.push("missing server-rendered page content");
    if (!document.querySelector('link[rel="stylesheet"]')) problems.push("missing initial stylesheet");
  } else {
    if (!/noindex/i.test(robots)) problems.push("missing noindex");
    if (document.head.querySelector('link[rel="canonical"]')) problems.push("utility/error page must not inherit a canonical");
  }
  const graphs = [];
  for (const script of document.querySelectorAll('script[type="application/ld+json"]')) {
    try { graphs.push(JSON.parse(script.textContent)); }
    catch { problems.push("invalid JSON-LD"); }
  }
  if (indexable && (url.pathname === "/" || /^\/(blog|learn)(\/|$)/.test(url.pathname)) && !graphs.length) {
    problems.push("missing server-rendered structured data");
  }
  return { document, problems, title, description, graphs };
}
