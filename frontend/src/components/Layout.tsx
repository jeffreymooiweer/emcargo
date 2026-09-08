import { Suspense, useEffect, useRef, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router";
import { useTranslation } from "react-i18next";
import { api, User } from "../api/client";
import { useBranding } from "../branding";
import { usePreferences } from "../settings/preferences";
import CommandMenu from "./CommandMenu";
import UpdateToast from "./UpdateToast";
import TwoFactorNudge, { clearTwoFactorNudge } from "./TwoFactorNudge";
import WhatsNewModal from "./WhatsNewModal";
import { CollapseIcon, GroupageIcon, HistoryIcon, HomeIcon, LibraryIcon, MenuIcon, MoreIcon, PlusIcon, RoadIcon, SettingsIcon, ShipmentsIcon, TripsIcon, UserIcon } from "./icons";

interface Props { user: User; onLogout: () => void }

/** One navigation tree shared by the desktop rail and the mobile drawer. */
export default function Layout({ user, onLogout }: Props) {
  const { t } = useTranslation();
  const { branding } = useBranding();
  const { mode, publicSettings } = usePreferences();
  const location = useLocation();
  const navigate = useNavigate();
  const open = mode === "open";
  const history = !open && !!publicSettings?.history_enabled;
  const admin = !open && user.role === "admin";
  const [menuOpen, setMenuOpen] = useState(false);
  const [railOpen, setRailOpen] = useState(true);
  const [version, setVersion] = useState<string | null>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const drawer = useRef<HTMLElement>(null);
  const previousPath = useRef(location.pathname);

  useEffect(() => { api.health().then((health) => setVersion(health.version)).catch(() => {}); }, []);
  useEffect(() => {
    setMenuOpen(false);
    // A new page starts at its heading, even when the previous form was long.
    // Wizard field edits and in-page steps do not change the pathname.
    if (previousPath.current !== location.pathname) {
      previousPath.current = location.pathname;
      window.scrollTo({ top: 0, left: 0, behavior: "instant" });
    }
  }, [location.pathname]);
  useEffect(() => {
    if (!menuOpen) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const targets = () => Array.from(drawer.current?.querySelectorAll<HTMLElement>("a[href], button:not([disabled]), summary") ?? []).filter((element) => element.getClientRects().length > 0);
    drawer.current?.querySelector<HTMLButtonElement>("button")?.focus();
    const keydown = (event: KeyboardEvent) => {
      if (event.key === "Escape") { event.preventDefault(); setMenuOpen(false); }
      if (event.key !== "Tab") return;
      const items = targets(); const first = items[0]; const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    };
    document.addEventListener("keydown", keydown);
    return () => { document.body.style.overflow = previousOverflow; document.removeEventListener("keydown", keydown); trigger.current?.focus(); };
  }, [menuOpen]);

  async function logout() {
    await api.logout(); clearTwoFactorNudge(); onLogout(); navigate("/login");
  }
  const destinations = [
    ...(history ? [{to: "/overzicht", label: t("nav.overview")}, {to: "/shipments", label: t("nav.shipments")}, {to: "/trips", label: t("nav.trips")}, {to: "/articles", label: t("nav.articles")}] : []),
    {to: "/", label: t("nav.new")}, {to: "/groupage", label: t("nav.groupage")},
    ...(admin ? [{to: "/materieel", label: t("nav.materieel")}, {to: "/users", label: t("nav.users")}, {to: "/audit", label: t("nav.audit")}] : []),
    {to: "/settings", label: t("nav.settings")}, {to: "/legal", label: t("nav.legal")},
  ];
  const currentLabel = location.pathname.startsWith("/wizard") ? t("nav.new") : destinations.find(item => item.to === location.pathname)?.label || t("studio.workspace");
  const name = branding.name || t("app.name");
  const versionLabel = version ? (version.startsWith("v") ? version : `v${version}`) : "";
  const brand = (compact = false) => <div className="emcargo-brand">
    <img src={branding.logo || "/emcargo.svg"} alt="" className="h-9 w-9 shrink-0 object-contain" />
    {!compact && <span className="truncate text-2xl font-semibold tracking-tight">{name}</span>}
  </div>;
  const linkClass = ({ isActive }: { isActive: boolean }) => `emcargo-nav-link ${isActive ? "emcargo-nav-active" : ""}`;
  type Icon = typeof HomeIcon;
  function link(to: string, label: string, Glyph: Icon, compact: boolean) {
    return <NavLink key={to} to={to} end={to === "/"} className={linkClass} title={compact ? label : undefined} aria-label={label} onClick={() => setMenuOpen(false)}>
      <Glyph className="h-[22px] w-[22px] shrink-0" />{!compact && <span className="truncate">{label}</span>}
    </NavLink>;
  }
  function navigation(compact = false) {
    return <>
      {history && link("/overzicht", t("nav.overview"), HomeIcon, compact)}
      {link("/", t("nav.new"), PlusIcon, compact)}
      {history && link("/shipments", t("nav.shipments"), ShipmentsIcon, compact)}
      {history && link("/trips", t("nav.trips"), TripsIcon, compact)}
      {!history && link("/groupage", t("nav.groupage"), GroupageIcon, compact)}
      {(history || admin) && (compact ? <>
        {history && link("/articles", t("nav.articles"), LibraryIcon, true)}
        {admin && link("/materieel", t("nav.materieel"), RoadIcon, true)}
      </> : <details className="emcargo-nav-group" open={["/articles", "/materieel"].includes(location.pathname) || undefined}>
        <summary className="emcargo-nav-link"><LibraryIcon className="h-[22px] w-[22px]" /><span>{t("nav.library")}</span><span className="ml-auto text-xs" aria-hidden="true">⌄</span></summary>
        <div className="emcargo-subnav">{history && link("/articles", t("nav.articles"), LibraryIcon, false)}{admin && link("/materieel", t("nav.materieel"), RoadIcon, false)}</div>
      </details>)}
      {compact ? <>
        {link("/settings", t("nav.settings"), SettingsIcon, true)}
        {history && link("/groupage", t("nav.groupage"), GroupageIcon, true)}
        {admin && link("/users", t("nav.users"), UserIcon, true)}
        {admin && link("/audit", t("nav.audit"), HistoryIcon, true)}
        {link("/legal", t("nav.legal"), MoreIcon, true)}
      </> : <details className="emcargo-nav-group" open={["/settings", "/users", "/audit", "/legal", "/groupage"].includes(location.pathname) || undefined}>
        <summary className="emcargo-nav-link"><SettingsIcon className="h-[22px] w-[22px]" /><span>{t("nav.manage")}</span><span className="ml-auto text-xs" aria-hidden="true">⌄</span></summary>
        <div className="emcargo-subnav">
          {history && link("/groupage", t("nav.groupage"), GroupageIcon, false)}
          {link("/settings", t("nav.settings"), SettingsIcon, false)}
          {admin && link("/users", t("nav.users"), UserIcon, false)}
          {admin && link("/audit", t("nav.audit"), HistoryIcon, false)}
          {link("/legal", t("nav.legal"), MoreIcon, false)}
        </div>
      </details>}
    </>;
  }
  const account = (compact = false) => <div className="emcargo-account">
    <div className="flex items-center gap-3">
      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-slate-200 text-xs font-semibold dark:bg-slate-700" aria-hidden="true">{open ? <UserIcon className="h-5 w-5" /> : user.username.slice(0, 2).toUpperCase()}</span>
      {!compact && <div className="min-w-0"><p className="truncate text-sm">{open ? t("nav.openMode") : user.username}</p>{versionLabel && <p className="mt-1 text-xs text-slate-500 dark:text-slate-400" aria-label={`${t("settings.version")} ${versionLabel}`}>{versionLabel}</p>}</div>}
    </div>
    {!open && <button onClick={() => void logout()} className="mt-3 min-h-[44px] w-full border-t border-slate-200 pt-3 text-left text-sm dark:border-slate-700" aria-label={t("nav.logout")}>{compact ? <span aria-hidden="true">↪</span> : t("nav.logout")}</button>}
  </div>;

  return <div className={`emcargo-shell ${railOpen ? "" : "emcargo-shell-folded"}`}>
    <a href="#main-content" className="skip-link">{t("nav.skipContent")}</a>
    <header className="emcargo-mobile-header">{brand()}<button ref={trigger} className="flex h-11 w-11 items-center justify-center" onClick={() => setMenuOpen(true)} aria-label={t("nav.openMenu")} aria-expanded={menuOpen}><MenuIcon className="h-7 w-7" /></button></header>
    <aside className="emcargo-sidebar">
      {brand(!railOpen)}
      <nav id="main-nav" aria-label={t("nav.menu")} className="emcargo-navigation">{navigation(!railOpen)}</nav>
      {account(!railOpen)}
      <button onClick={() => setRailOpen((value) => !value)} className="emcargo-rail-toggle" aria-controls="main-nav" aria-expanded={railOpen} aria-label={railOpen ? t("nav.collapseMenu") : t("nav.expandMenu")}><CollapseIcon className={`h-4 w-4 ${railOpen ? "" : "rotate-180"}`} /></button>
    </aside>
    <main id="main-content" tabIndex={-1} className="emcargo-main"><div className="workspace-bar"><div className="workspace-location"><span>{t("studio.workspace")}</span><span aria-hidden="true">/</span><strong>{currentLabel}</strong></div><CommandMenu destinations={destinations} /></div><Suspense fallback={<div className="route-loading" role="status">{t("wizard.loading")}</div>}><Outlet /></Suspense></main>
    {!open && <><WhatsNewModal /><UpdateToast user={user} /><TwoFactorNudge user={user} /></>}
    {menuOpen && <div className="fixed inset-0 z-50 md:hidden" role="dialog" aria-modal="true" aria-label={t("nav.menu")}>
      <div className="absolute inset-0 bg-black/60" onClick={() => setMenuOpen(false)} />
      <aside ref={drawer} className="emcargo-mobile-drawer">
        <div className="flex items-center justify-between p-4">{brand()}<button className="h-11 w-11 text-2xl" onClick={() => setMenuOpen(false)} aria-label={t("nav.closeMenu")}>×</button></div>
        <nav className="emcargo-navigation">{navigation()}</nav>{account()}
      </aside>
    </div>}
  </div>;
}
