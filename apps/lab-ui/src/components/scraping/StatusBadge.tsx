import type { DerivedStatus } from "./useScraping";

const LABELS: Record<DerivedStatus, string> = {
  idle: "Inactivo",
  running: "Ejecutando",
  completed: "Completado",
  error: "Error",
};

const STYLES: Record<DerivedStatus, string> = {
  idle: "bg-white/5 text-muted-foreground border-border",
  running: "bg-accent/15 text-accent border-accent/30 animate-pulse",
  completed: "bg-success/15 text-success border-success/30",
  error: "bg-destructive/15 text-destructive border-destructive/30",
};

export function StatusBadge({
  status,
  runningLabel,
}: {
  status: DerivedStatus;
  runningLabel?: string;
}) {
  const label = status === "running" && runningLabel ? runningLabel : LABELS[status];
  return (
    <span
      className={`px-2.5 py-0.5 rounded text-[10px] uppercase tracking-widest font-semibold border ${STYLES[status]}`}
    >
      {label}
    </span>
  );
}
