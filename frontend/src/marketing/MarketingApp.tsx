import { Route, Routes } from "react-router-dom";
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

export default function MarketingApp() {
  return (
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
  );
}
