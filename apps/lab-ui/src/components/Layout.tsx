import { NavLink, Outlet } from "react-router-dom";
import {
  Activity, Boxes, Cpu, Database, GitCompareArrows, Hammer,
  Rocket, RotateCcw, Search, Users,
} from "lucide-react";

const nav = [
  { to: "/dashboard",     label: "Dashboard",     icon: Activity },
  { to: "/models",        label: "Models",        icon: Boxes },
  { to: "/training",      label: "Training",      icon: Hammer },
  { to: "/hp-search",     label: "HP Search",     icon: Search },
  { to: "/scraping",      label: "Scraping",      icon: Database },
  { to: "/predictions",   label: "Predictions",   icon: Cpu },
  { to: "/fighters",      label: "Fighters",      icon: Users },
  { to: "/compare",       label: "Compare",       icon: GitCompareArrows },
  { to: "/publish",       label: "Publish",       icon: Rocket },
  { to: "/recalculation", label: "Recalculation", icon: RotateCcw },
];

export default function Layout() {
  return (
    <div className="flex h-screen overflow-hidden">
      <aside className="w-[220px] border-r border-border bg-sidebar flex flex-col flex-shrink-0">
        <div className="px-5 py-6 border-b border-border flex items-center gap-2">
          <span className="text-accent text-2xl font-bold leading-none">⬡</span>
          <span
            className="text-foreground font-bold tracking-wide leading-tight"
            style={{ fontFamily: "'Oswald', sans-serif", fontSize: "1.1rem", letterSpacing: "0.05em" }}
          >
            UFC<br />
            <span className="text-accent">LAB</span>
          </span>
        </div>
        <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
          {nav.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                [
                  "flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-all duration-150",
                  isActive
                    ? "bg-accent/10 text-foreground border-l-2 border-accent pl-[calc(0.75rem-2px)]"
                    : "text-muted-foreground hover:text-muted hover:bg-border/50",
                ].join(" ")
              }
            >
              {({ isActive }) => (
                <>
                  <Icon size={16} className={isActive ? "text-accent" : ""} />
                  <span>{label}</span>
                </>
              )}
            </NavLink>
          ))}
        </nav>
        <div className="px-4 py-4 border-t border-border text-xs text-muted-foreground">
          v0.1.0 · :8101
        </div>
      </aside>
      <main className="flex-1 overflow-y-auto px-8 py-6">
        <Outlet />
      </main>
    </div>
  );
}
