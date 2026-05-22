import { Check } from "lucide-react";
import type { ScrapingStatus } from "../../api/client";
import { deriveStatus } from "./useScraping";

interface PipelineProgressProps {
  status: ScrapingStatus | undefined;
}

// Mirrors lab-api's real flow (see scraping router PIPELINE_PHASES), NOT the
// legacy backend's A–E file pipeline. The backend reports the active `phase` key.
const PHASES: { key: string; label: string }[] = [
  { key: "scraping", label: "Scraping" },
  { key: "ingest", label: "Ingesta" },
  { key: "tapology", label: "Tapology" },
  { key: "features", label: "Features" },
];

function stepState(
  idx: number,
  currentIdx: number,
  derived: string,
): "completed" | "active" | "pending" {
  if (derived === "completed" || currentIdx >= PHASES.length) return "completed";
  if (idx < currentIdx) return "completed";
  if (idx === currentIdx && derived === "running") return "active";
  return "pending";
}

export function PipelineProgress({ status }: PipelineProgressProps) {
  const derived = deriveStatus(status);
  const phase = status?.phase ?? null;
  // "done" (or a completed run) means every phase is finished.
  const currentIdx =
    phase === "done" || derived === "completed"
      ? PHASES.length
      : PHASES.findIndex((p) => p.key === phase);

  const current = status?.progress_current ?? 0;
  const total = status?.progress_total ?? 0;
  const isRunning = derived === "running";
  const pct = total > 0 ? Math.min((current / total) * 100, 100) : 0;

  return (
    <div className="rounded-lg border border-border bg-card p-5 space-y-5">
      <h2 className="text-foreground font-semibold text-base">Pipeline</h2>

      {/* Stepper */}
      <div className="flex items-start gap-0">
        {PHASES.map((step, idx) => {
          const state = stepState(idx, currentIdx, derived);
          const isLast = idx === PHASES.length - 1;
          return (
            <div key={step.key} className="flex items-start flex-1 min-w-0">
              <div className="flex flex-col items-center flex-1 min-w-0">
                <div
                  className={[
                    "flex items-center justify-center rounded-full w-8 h-8 text-xs font-bold shrink-0 transition-all duration-300",
                    state === "completed"
                      ? "bg-success text-background"
                      : state === "active"
                        ? "bg-accent text-accent-foreground animate-pulse ring-2 ring-accent/40"
                        : "bg-white/5 text-muted-foreground",
                  ].join(" ")}
                >
                  {state === "completed" ? <Check className="h-4 w-4" /> : idx + 1}
                </div>
                <span
                  className={[
                    "mt-1.5 text-[10px] text-center leading-tight px-0.5 truncate w-full",
                    state === "completed"
                      ? "text-success"
                      : state === "active"
                        ? "text-accent font-semibold"
                        : "text-muted-foreground",
                  ].join(" ")}
                >
                  {step.label}
                </span>
              </div>
              {!isLast && (
                <div className="flex-shrink-0 w-4 mt-4">
                  <div
                    className={[
                      "h-0.5 w-full transition-colors duration-300",
                      idx < currentIdx ? "bg-success" : "bg-border",
                    ].join(" ")}
                  />
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Letter progress bar (only meaningful during the scraping phase) */}
      {isRunning && total > 0 && (
        <div className="space-y-1.5">
          <div className="flex justify-between text-xs text-muted-foreground">
            <span className="truncate pr-2">{status?.step || "Procesando…"}</span>
            <span className="tabular-nums shrink-0">
              {current} / {total}
            </span>
          </div>
          <div className="h-1.5 w-full rounded-full bg-white/5 overflow-hidden">
            <div
              className="h-full rounded-full bg-accent transition-all duration-500"
              style={{ width: `${pct}%` }}
            />
          </div>
        </div>
      )}

      {derived === "completed" && (
        <p className="text-success text-xs text-center font-medium">
          Pipeline completado correctamente
        </p>
      )}
      {derived === "error" && (
        <p className="text-destructive text-xs text-center font-medium">
          El pipeline encontró un error
        </p>
      )}
    </div>
  );
}
