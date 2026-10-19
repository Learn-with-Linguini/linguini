import { useEffect } from "react";
import { Route, Routes, useLocation } from "react-router-dom";
import { FullReload } from "../components/FullReload";
import BlogIndex from "./pages/blog/BlogIndex";
import BlogPost from "./pages/blog/BlogPost";
import CreditsPage from "./pages/CreditsPage";
import HomePage from "./pages/HomePage";
import LearnPage from "./pages/learn/LearnPage";
import PrivacyPage from "./pages/legal/PrivacyPage";
import SharePage from "./pages/SharePage";
import TermsPage from "./pages/legal/TermsPage";
import "./styles/globals.css";

function ScrollToTop() {
  const { pathname, search, hash } = useLocation();

  useEffect(() => {
    if (hash) {
      const id = hash.replace(/^#/, "");
      const element = document.getElementById(id);
      if (element) {
        element.scrollIntoView({ behavior: "smooth" });
        return;
      }
    }
    window.scrollTo({ top: 0, left: 0, behavior: "instant" });
  }, [pathname, search, hash]);

  return null;
}

export default function MarketingApp() {
  return (
    <>
      <ScrollToTop />
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/blog" element={<BlogIndex />} />
        <Route path="/blog/:slug" element={<BlogPost />} />
        <Route path="/learn/:language" element={<LearnPage />} />
        <Route path="/privacy" element={<PrivacyPage />} />
        <Route path="/terms" element={<TermsPage />} />
        <Route path="/credits" element={<CreditsPage />} />
        <Route path="/share" element={<SharePage />} />
        <Route path="*" element={<FullReload />} />
      </Routes>
    </>
  );
}
