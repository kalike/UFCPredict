import { ReactNode } from "react";

export function PageHeader({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <header className="mb-6">
      <h2 className="font-display text-3xl tracking-wide uppercase">{title}</h2>
      {subtitle && <p className="mt-1 text-sm text-[var(--color-muted)]">{subtitle}</p>}
    </header>
  );
}

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div className={`rounded-lg border border-border bg-card p-5 ${className}`}>
      {children}
    </div>
  );
}

export function Button({
  onClick, disabled, children, variant = "primary",
}: {
  onClick?: () => void; disabled?: boolean; children: ReactNode;
  variant?: "primary" | "secondary" | "danger";
}) {
  const styles =
    variant === "primary"
      ? "bg-accent text-accent-foreground font-semibold shadow-[var(--shadow-primary-btn)] hover:bg-accent-hi hover:shadow-[var(--shadow-primary-btn-hi)]"
      : variant === "danger"
      ? "bg-red-700 text-white hover:bg-red-600"
      : "bg-white/5 text-[var(--color-foreground)] hover:bg-white/10";
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${styles}`}
    >
      {children}
    </button>
  );
}

export function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className={`w-full bg-[var(--color-background)] border border-[var(--color-border)] rounded-md px-3 py-1.5 text-sm focus:border-[var(--color-accent)] focus:outline-none ${props.className ?? ""}`}
    />
  );
}

export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse bg-white/5 rounded-md ${className}`} />;
}

export function Badge({ children, tone = "default" }: { children: ReactNode; tone?: "default" | "accent" | "gold" | "muted" }) {
  const styles =
    tone === "accent" ? "bg-[var(--color-accent)]/15 text-[var(--color-accent)]"
    : tone === "gold" ? "bg-[var(--color-gold)]/15 text-[var(--color-gold)]"
    : tone === "muted" ? "bg-white/5 text-[var(--color-muted)]"
    : "bg-white/10";
  return <span className={`px-2 py-0.5 rounded text-[10px] uppercase tracking-widest ${styles}`}>{children}</span>;
}
