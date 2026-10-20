import { Navigate, Outlet, Route, Routes, useLocation } from "react-router-dom";
import { AppShell, FocusShell } from "./components/AppShell";
import { Home } from "./pages/Home";
import { Onboarding } from "./pages/Onboarding";
import { Login } from "./pages/Login";
import { PracticeSelect } from "./pages/PracticeSelect";
import { PracticeAnalysis } from "./pages/PracticeAnalysis";
import { MicTest } from "./pages/MicTest";
import { Learn } from "./pages/Learn";
import { VocabularyPreview } from "./pages/VocabularyPreview";
import { LearningTaskPage, VocabularySceneReview } from "./pages/LearningTaskPage";
import { ISpyPhase1 } from "./pages/ISpyPhase1";
import { ISpyPhase2 } from "./pages/ISpyPhase2";
import { ISpyModes } from "./pages/ISpyModes";
import { ISpyPlay } from "./pages/ISpyPlay";
import { DailyChallengePage } from "./pages/DailyChallengePage";
import { ISpyResults } from "./pages/ISpyResults";
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
import { Contact } from "./pages/Contact";
import { Payment } from "./pages/Payment";
import { ResetPassword } from "./pages/ResetPassword";
import { AppStateProvider } from "./state/AppState";
import { useAuth } from "./state/Auth";
import { LoadingScreen } from "./components/LoadingScreen";
import { Rooms } from "./pages/Rooms";
import { Room } from "./pages/Room";
import { FullReload } from "./components/FullReload";
import { isMarketingPath } from "./marketing/paths";

function RequireAuth() {
  const { session, loading } = useAuth();
  const location = useLocation();
  if (loading) return <LoadingScreen label="Checking your account…" />;
  if (import.meta.env.DEV) return <Outlet />;
  if (!session) return <Navigate to="/login" replace state={{ from: `${location.pathname}${location.search}` }} />;
  return <Outlet />;
}

function AuthenticatedApp() {
  return <AppStateProvider><Outlet /></AppStateProvider>;
}

/** Keep existing private invitation URLs while placing their lobby under I-Spy. */
function RoomInvitationRoute() {
  const { search, state } = useLocation();
  return <Navigate to={`/ispy/friends${search}`} state={state} replace />;
}

function OnboardingRoute() {
  const { session, loading } = useAuth();
  if (loading) return <LoadingScreen label="Preparing onboarding…" />;
  if (!session) return <Navigate to="/login?mode=signup" replace />;
  return <AppStateProvider><Onboarding /></AppStateProvider>;
}

function UnknownRoute() {
  const { pathname } = useLocation();
  return isMarketingPath(pathname) ? <FullReload /> : <Navigate to="/home" replace />;
}

export default function App() {
  return (
    <Routes>
      <Route element={<FocusShell />}>
        <Route path="/" element={<FullReload />} />
        <Route path="/login" element={<Login />} />
        <Route path="/reset-password" element={<ResetPassword />} />
        <Route path="/onboarding" element={<OnboardingRoute />} />
        <Route path="/contact" element={<Contact />} />
      </Route>
      <Route element={<RequireAuth />}>
        <Route element={<AuthenticatedApp />}>
          <Route element={<FocusShell />}>
            <Route path="/payment" element={<Payment />} />
            <Route path="/rooms/:roomId" element={<Room />} />
        <Route path="/practice/sessions/:sessionId" element={<SessionRoute />}>
          <Route path="analysis" element={<PracticeAnalysis />} />
          <Route path="mic-test" element={<MicTest />} />
          <Route path="learn" element={<Learn />} />
          <Route path="learn/vocabulary-preview" element={<VocabularyPreview />} />
          <Route path="learn/:taskId" element={<LearningTaskPage />} />
          <Route path="review" element={<VocabularySceneReview />} />
          <Route path="ispy-1" element={<ISpyPhase1 />} />
          <Route path="ispy-2" element={<ISpyPhase2 />} />
          <Route path="summary" element={<SessionSummary />} />
        </Route>
        <Route path="/ispy/games/:sessionId" element={<SessionRoute />}>
          <Route path="clues" element={<ISpyPhase1 />} />
          <Route path="describe" element={<ISpyPhase2 />} />
          <Route path="results" element={<ISpyResults />} />
        </Route>
        <Route path="/practice/:sceneId/*" element={<SceneRoute />} />
          </Route>
          <Route element={<AppShell />}>
        <Route path="/home" element={<Home />} />
        <Route path="/rooms" element={<RoomInvitationRoute />} />
        <Route path="/practice" element={<PracticeSelect />} />
        <Route path="/ispy" element={<ISpyModes />} />
        <Route path="/ispy/play" element={<ISpyPlay />} />
        <Route path="/ispy/challenge" element={<DailyChallengePage />} />
        <Route path="/ispy/friends" element={<Rooms />} />
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
      <Route path="*" element={<UnknownRoute />} />
    </Routes>
  );
}
