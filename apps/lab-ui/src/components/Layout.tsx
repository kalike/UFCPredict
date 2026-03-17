import { NavLink, Outlet } from "react-router-dom";
import {
  Activity, Boxes, Cpu, Database, GitCompareArrows, Hammer, ListChecks,
  Rocket, Search, Users,
} from "lucide-react";

const nav = [
  { to: "/dashboard",     label: "Dashboard",     icon: Activity },
  { to: "/models",        label: "Models",        icon: Boxes },
  { to: "/training",      label: "Training",      icon: Hammer },
  { to: "/hp-search",     label: "HP Search",     icon: Search },
  { to: "/combo-search",  label: "Combo Search",  icon: ListChecks },
  { to: "/scraping",      label: "Scraping",      icon: Database },
  { to: "/predictions",   label: "Predictions",   icon: Cpu },
  { to: "/fighters",      label: "Fighters",      icon: Users },
  { to: "/compare",       label: "Compare",       icon: GitCompareArrows },
  { to: "/publish",       label: "Publish",       icon: Rocket },
];

export default function Layout() {
  return (
    <div className="flex h-screen overflow-hidden">
      <aside className="w-56 border-r border-[var(--color-border)] bg-[var(--color-card)] flex flex-col">
        <div className="px-4 py-5 border-b border-[var(--color-border)]">
          <h1 className="font-display text-xl tracking-wider text-[var(--color-accent)]">
            UFC&nbsp;LAB
          </h1>
          <p className="text-[10px] text-[var(--color-muted)] mt-1 uppercase tracking-widest">
            Broadcast Quant
          </p>
        </div>
        <nav className="flex-1 py-2 overflow-y-auto">
          {nav.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                [
                  "flex items-center gap-3 px-4 py-2 text-sm transition-colors",
                  isActive
                    ? "bg-[var(--color-accent)]/10 text-[var(--color-accent)] border-l-2 border-[var(--color-accent)]"
                    : "text-[var(--color-foreground)]/80 hover:bg-white/5",
                ].join(" ")
              }
            >
              <Icon size={16} />
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="px-4 py-3 border-t border-[var(--color-border)] text-[10px] text-[var(--color-muted)]">
          v0.1.0 · :8101
        </div>
      </aside>
      <main className="flex-1 overflow-y-auto px-8 py-6">
        <Outlet />
      </main>
    </div>
  );
}
