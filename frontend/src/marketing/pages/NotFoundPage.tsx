import { SiteFooter } from "../components/SiteFooter";
import { SiteHeader } from "../components/SiteHeader";
import { PageMeta } from "../lib/seo";

export default function NotFoundPage() {
  return (
    <>
      <PageMeta title="Page not found" description="That page may have moved. Return to Linguini to learn a language from everyday photos, explore the blog or try a photo lesson." path="/404" noIndex />
      <SiteHeader />
      <main className="container" id="main">
        <section aria-labelledby="not-found-title">
          <h1 id="not-found-title">Page not found</h1>
          <p>That page may have moved. Head back to Linguini and keep learning from your day.</p>
          <a className="btn" href="/">Back to Linguini</a>
        </section>
      </main>
      <SiteFooter />
    </>
  );
}
