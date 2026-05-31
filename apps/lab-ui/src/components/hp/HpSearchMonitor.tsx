import type { HpStatus } from "../../api/client";
import { useHpTrials } from "./useHpSearch";
import { TrialsTable } from "./TrialsTable";

interface HpSearchMonitorProps {
  status: HpStatus | undefined;
  nTrials: number;
  queueIndex: number;
  queueTotal: number;
  live: boolean;
}

export function HpSearchMonitor({ status, nTrials, queueIndex, queueTotal, live }: HpSearchMonitorProps) {
  const studyId = status?.study_id ?? null;
  const { data: trials } = useHpTrials(studyId, live);

  const running = !!status?.is_running;
  const isQueue = queueTotal > 1;
  const completed = status?.completed_trials ?? 0;
  const total = status?.n_trials || nTrials;
  const pct = total > 0 ? Math.min(100, Math.round((completed / total) * 100)) : 0;
  const objectives = status?.objectives ?? [];

  if (!running && (!trials || trials.length === 0)) {
    return (
      <div className="text-center py-12 text-muted-foreground text-sm">
        No hay búsqueda activa. Configura y lanza una búsqueda desde el formulario.
        <br />
        Los resultados de cada job quedan abajo, en «Resultados de jobs».
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-foreground" style={{ fontFamily: "'Oswald', sans-serif" }}>
          {running
            ? isQueue
              ? `Job ${queueIndex + 1}/${queueTotal}: ${status?.model_short ?? "…"}`
              : `Búsqueda HP: ${status?.model_short ?? "…"}`
            : "Búsqueda en reposo"}
          {running && ` — Trial ${completed}/${total}`}
        </h3>
        {status?.best_value != null && (
          <span className="text-xs text-muted-foreground">
            Best: <strong className="text-accent display-num">{(status.best_value * 100).toFixed(1)}%</strong>
          </span>
        )}
      </div>

      {/* Objectives */}
      {objectives.length > 0 && (
        <div className="flex flex-wrap gap-2 text-[11px] text-muted-foreground">
          <span className="font-medium">Objetivos:</span>
          {objectives.map((o) => (
            <span key={o.metric} className="px-1.5 py-0.5 rounded bg-accent/15 text-accent">
              {o.metric} ({o.direction === "minimize" ? "↓" : "↑"})
            </span>
          ))}
        </div>
      )}

      {/* Step */}
      {running && status?.step && (
        <div className="text-xs text-accent bg-accent/5 border border-accent/20 rounded-lg px-3 py-2 animate-pulse">
          {status.step}
        </div>
      )}

      {/* Progress bar */}
      {running && (
        <div className="w-full bg-border/30 rounded-full h-2.5">
          <div className="bg-accent h-2.5 rounded-full transition-all duration-300" style={{ width: `${pct}%` }} />
        </div>
      )}

      {/* Error */}
      {status?.error && (
        <div className="text-destructive text-xs bg-destructive/10 border border-destructive/20 rounded-lg px-3 py-2">
          {status.error}
        </div>
      )}

      {/* Live trials (read-only — adoption happens in "Resultados de jobs") */}
      <TrialsTable trials={trials ?? []} />
    </div>
  );
}
