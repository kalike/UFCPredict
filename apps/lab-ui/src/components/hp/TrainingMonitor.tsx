import type { TrainStatus } from "../../api/client";

interface TrainingMonitorProps {
  status: TrainStatus | undefined;
  onDismiss: () => void;
}

export function TrainingMonitor({ status, onDismiss }: TrainingMonitorProps) {
  if (!status) return null;
  const running = status.is_running;

  return (
    <div className="border border-accent/20 rounded-lg px-4 py-3 bg-accent/5 space-y-2">
      <div className="flex items-center justify-between text-xs">
        <span className="font-medium text-foreground" style={{ fontFamily: "'Oswald', sans-serif" }}>
          {running
            ? `Entrenando adoptados: ${status.model_short ?? "…"}` +
              (status.n_jobs ? ` (${(status.job_index ?? 0) + 1}/${status.n_jobs})` : "")
            : "Entrenamiento completado"}
        </span>
        {running ? (
          <span className="text-muted-foreground display-num">{Math.round(status.pct)}%</span>
        ) : (
          <button
            type="button"
            onClick={onDismiss}
            className="text-[11px] text-muted-foreground hover:text-foreground transition-colors"
          >
            Cerrar
          </button>
        )}
      </div>

      {running && (
        <div className="w-full bg-border/30 rounded-full h-1.5">
          <div className="bg-accent h-1.5 rounded-full transition-all duration-300" style={{ width: `${status.pct}%` }} />
        </div>
      )}

      {status.step && <p className="text-[11px] text-muted-foreground truncate">{status.step}</p>}

      {status.error && <p className="text-[11px] text-destructive">{status.error}</p>}

      {status.results && status.results.length > 0 && (
        <div className="text-[11px] space-y-0.5">
          {status.results.map((r, i) => (
            <div key={i} className={r.error ? "text-destructive" : "text-success"}>
              {r.model_short}: {r.error
                ? "Error"
                : `Acc ${((r.accuracy ?? 0) * 100).toFixed(1)}% · ` +
                  `RW ${r.realworld_accuracy != null ? (r.realworld_accuracy * 100).toFixed(1) + "%" : "—"}` +
                  (r.version_idx != null ? ` · v${r.version_idx}` : "")}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
