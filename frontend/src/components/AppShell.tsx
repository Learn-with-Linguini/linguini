import { NavLink, Outlet, useLocation } from "react-router-dom";
import { BookIcon, CameraIcon, HomeIcon, JournalIcon, PersonIcon } from "./icons";
import { BrandBar } from "./ui";
import { BackActionProvider, useRegisteredBackAction } from "./BackAction";
import { useAuth } from "../state/Auth";

const items = [
  { to: "/home", label: "Home", Icon: HomeIcon },
  { to: "/practice", label: "Practice", Icon: CameraIcon },
  { to: "/vocabulary", label: "Vocabulary", Icon: BookIcon },
  { to: "/journal", label: "Journal", Icon: JournalIcon },
  { to: "/profile", label: "Profile", Icon: PersonIcon },
];

export function AppShell() {
  const { pathname } = useLocation();
  const isDetailPage =
    pathname === "/journal/new" ||
    /^\/journal\/[^/]+$/.test(pathname) ||
    pathname === "/profile/edit";
  const usesWideCanvas =
    ["/home", "/practice", "/vocabulary", "/journal"].includes(pathname) ||
    pathname === "/journal/new" ||
    /^\/journal\/[^/]+$/.test(pathname);

  return (
    <div className="shell shell--app">
      <BrandBar back={isDetailPage} homeTo="/home" />
      <main className={`shell__content${usesWideCanvas ? " shell__content--desktop-wide" : ""}`}>
        <Outlet />
      </main>
      <nav className="bottom-nav" aria-label="Main">
        {items.map(({ to, label, Icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) => `bottom-nav__item${isActive ? " is-active" : ""}`}
          >
            <Icon />
            <span>{label}</span>
          </NavLink>
        ))}
      </nav>
    </div>
  );
}

/** Full-bleed shell for focused flows (onboarding, practice steps, I-Spy). */
export function FocusShell() {
  return (
    <BackActionProvider>
      <FocusShellView />
    </BackActionProvider>
  );
}

function FocusShellView() {
  const { pathname } = useLocation();
  const { session } = useAuth();
  const backAction = useRegisteredBackAction();
  const usesWideCanvas = pathname.endsWith("/analysis");

  return (
    <div className="shell shell--focus">
      <BrandBar back={pathname !== "/"} onBack={backAction.onBack} backLabel={backAction.backLabel} homeTo={session ? "/home" : "/"} />
      <main
        className={`shell__content${usesWideCanvas ? " shell__content--desktop-wide" : ""}`}
        style={{ paddingBottom: "var(--space-8)" }}
      >
        <Outlet />
      </main>
    </div>
  );
}
