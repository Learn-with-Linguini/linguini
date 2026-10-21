import { SiteFooter } from "../components/SiteFooter";
import { SiteHeader } from "../components/SiteHeader";

export default function NotFoundPage() {
  return (
    <>
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
