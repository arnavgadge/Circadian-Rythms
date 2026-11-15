import { useState } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import { BrandLockup } from "../atlas/BrandMark";
import { Icon, type IconName } from "../atlas/Icon";
import { SidebarLandscape } from "../atlas/Illustrations";

interface SidebarProps {
  participantId: number | null;
  participantCode?: string | null;
  synthetic?: boolean;
  devMode: boolean;
  onToggleDevMode: () => void;
  versionLabel?: string | null;
}

/**
 * The persistent evergreen navigation for every participant page.
 * Research Mode keeps its original behaviour -- a real checkbox toggle
 * (not a separate page) that reveals the raw-data panels -- restyled
 * as a switch in the navigation list.
 */
export function Sidebar({ participantId, participantCode, synthetic = false, devMode, onToggleDevMode, versionLabel }: SidebarProps) {
  const location = useLocation();
  // The mobile drawer is "open for" one path; navigating anywhere else closes it.
  const [openForPath, setOpenForPath] = useState<string | null>(null);
  const open = openForPath === location.pathname;
  const dateParam = new URLSearchParams(location.search).get("date");
  const dateSuffix = dateParam ? `?date=${dateParam}` : "";

  const items: Array<{ to: string; label: string; icon: IconName }> =
    participantId !== null
      ? [
          { to: `/dashboard/${participantId}${dateSuffix}`, label: "Dashboard", icon: "dashboard" },
          { to: `/log/${participantId}${dateSuffix}`, label: "Log Behavior", icon: "pencil" },
          { to: `/history/${participantId}`, label: "History", icon: "history" },
          { to: `/interventions/${participantId}`, label: "Interventions", icon: "interventions" },
        ]
      : [];
  items.push({ to: "/demo", label: "30-Day Research Demo", icon: "calendar" });

  return (
    <aside className="sidebar" data-open={open ? "true" : "false"}>
      <div className="sidebar__top">
        <Link to="/" className="sidebar__brand" aria-label="CircadianIQ home">
          <BrandLockup tone="dark" />
        </Link>
        <button
          type="button"
          className="sidebar__menu-button"
          aria-expanded={open}
          aria-controls="sidebar-drawer"
          onClick={() => setOpenForPath(open ? null : location.pathname)}
        >
          <Icon name="menu" size={16} /> Menu
        </button>
      </div>

      <div className="sidebar__drawer" id="sidebar-drawer">
        <nav aria-label="Main" className="sidebar__nav">
          <ul>
            {items.map((item) => (
              <li key={item.label}>
                <NavLink to={item.to} className="nav-item">
                  <Icon name={item.icon} size={17} />
                  {item.label}
                </NavLink>
              </li>
            ))}
            <li>
              <label className="nav-item nav-toggle">
                <Icon name="research" size={17} />
                Research Mode
                <input type="checkbox" checked={devMode} onChange={onToggleDevMode} />
                <span className="nav-toggle__switch" aria-hidden="true" />
              </label>
            </li>
          </ul>
        </nav>

        {participantId !== null && (
          <div className="sidebar__participant">
            Participant #{participantId}
            {participantCode && ` · ${participantCode}`}
            {synthetic && <span className="sidebar__synthetic">Synthetic research participant</span>}
            <br />
            <Link to="/">Switch participant</Link>
          </div>
        )}
      </div>

      <div className="sidebar__bottom" aria-hidden={versionLabel ? undefined : true}>
        <SidebarLandscape />
        <p className="sidebar__version">
          {versionLabel && (
            <>
              {versionLabel}
              <br />
            </>
          )}
          Research Demo
        </p>
      </div>
    </aside>
  );
}
