import { Navigate, Outlet, Route, Routes, useLocation } from "react-router-dom";
import { AppShell, FocusShell } from "./components/AppShell";
import { Home } from "./pages/Home";
import { Welcome } from "./pages/Welcome";
import { Onboarding } from "./pages/Onboarding";
import { Login } from "./pages/Login";
import { PracticeSelect } from "./pages/PracticeSelect";
import { PracticeAnalysis } from "./pages/PracticeAnalysis";
import { MicTest } from "./pages/MicTest";
import { Learn } from "./pages/Learn";
import { LearningTaskPage } from "./pages/LearningTaskPage";
import { ISpyPhase1 } from "./pages/ISpyPhase1";
import { ISpyPhase2 } from "./pages/ISpyPhase2";
import { SessionSummary } from "./pages/SessionSummary";
import { Vocabulary } from "./pages/Vocabulary";
import { Journal } from "./pages/Journal";
import { JournalEntryPage } from "./pages/JournalEntryPage";
import { JournalNew } from "./pages/JournalNew";
import { Profile } from "./pages/Profile";
import { SceneRoute } from "./components/SceneRoute";
import { SessionRoute } from "./components/SessionRoute";
import { ProfileEdit } from "./pages/ProfileEdit";
import { Progress } from "./pages/Progress";
import { AppStateProvider } from "./state/AppState";
import { useAuth } from "./state/Auth";
import { LoadingScreen } from "./components/LoadingScreen";

function RequireAuth() {
 
  const { session, loading } = useAuth();
  const location = useLocation();
  if (import.meta.env.DEV) return <Outlet />;
  if (loading) return <LoadingScreen label="Checking your account…" />;
  if (!session) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  return <Outlet />;
}

function AuthenticatedApp() {
  return <AppStateProvider><Outlet /></AppStateProvider>;
}

function OnboardingRoute() {
  const { session, loading } = useAuth();
  if (loading) return <LoadingScreen label="Preparing onboarding…" />;
  if (!session) return <Navigate to="/login?mode=signup" replace />;
  return <AppStateProvider><Onboarding /></AppStateProvider>;
}

export default function App() {
  return (
    <Routes>
      <Route element={<FocusShell />}>
        <Route path="/" element={<Welcome />} />
        <Route path="/login" element={<Login />} />
        <Route path="/onboarding" element={<OnboardingRoute />} />
      </Route>
      <Route element={<RequireAuth />}>
        <Route element={<AuthenticatedApp />}>
          <Route element={<FocusShell />}>
        <Route path="/practice/sessions/:sessionId" element={<SessionRoute />}>
          <Route path="analysis" element={<PracticeAnalysis />} />
          <Route path="mic-test" element={<MicTest />} />
          <Route path="learn" element={<Learn />} />
          <Route path="learn/:taskId" element={<LearningTaskPage />} />
          <Route path="ispy-1" element={<ISpyPhase1 />} />
          <Route path="ispy-2" element={<ISpyPhase2 />} />
          <Route path="summary" element={<SessionSummary />} />
        </Route>
        <Route path="/practice/:sceneId/*" element={<SceneRoute />} />
          </Route>
          <Route element={<AppShell />}>
        <Route path="/home" element={<Home />} />
        <Route path="/practice" element={<PracticeSelect />} />
        <Route path="/progress" element={<Progress />} />
        <Route path="/vocabulary" element={<Vocabulary />} />
        <Route path="/journal" element={<Journal />} />
        <Route path="/journal/new" element={<JournalNew />} />
        <Route path="/journal/new/:date" element={<JournalNew />} />
        <Route path="/journal/:entryId" element={<JournalEntryPage />} />
        <Route path="/profile" element={<Profile />} />
        <Route path="/profile/edit" element={<ProfileEdit />} />
          </Route>
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/home" replace />} />
    </Routes>
  );
}
