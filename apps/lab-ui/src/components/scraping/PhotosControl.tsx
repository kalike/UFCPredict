import { motion } from "framer-motion";
import { Loader2, Image as ImageIcon } from "lucide-react";
import { fmtDate } from "../../lib/formatters";
import {
  deriveStatus,
  usePhotosStatus,
  useStartPhotos,
} from "./useScraping";
import { StatusBadge } from "./StatusBadge";

export function PhotosControl() {
  const { data } = usePhotosStatus();
  const startMutation = useStartPhotos();

  const status = deriveStatus(data);
  const isRunning = status === "running";
  const lastRun = data?.finished_at ?? data?.started_at;
  const busy = isRunning || startMutation.isPending;

  const total = data?.progress_total ?? 0;
  const current = data?.progress_current ?? 0;
  const pct = total > 0 ? Math.round((current / total) * 100) : 0;

  // lab-api returns the download summary under `counts` once finished.
  const result = data?.counts as
    | { ok?: number; skip?: number; not_found?: number; error?: number; no_image?: number }
    | null
    | undefined;

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay: 0.05 }}
      className="rounded-lg border border-border bg-card p-5 space-y-4"
    >
      <div className="flex items-center justify-between gap-4">
        <div className="space-y-1">
          <h2 className="text-foreground font-semibold text-base">Descarga de fotos</h2>
          <p className="text-muted-foreground text-xs">
            Incremental · luchadores activos últimos 3 años
          </p>
          {lastRun && (
            <p className="text-muted-foreground text-xs">
              Última ejecución: {fmtDate(lastRun)}
            </p>
          )}
        </div>
        <StatusBadge status={status} runningLabel="Descargando" />
      </div>

      {data?.error && (
        <p className="text-destructive text-sm rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 break-words">
          {data.error}
        </p>
      )}

      {isRunning && (
        <div className="space-y-1.5">
          <p className="text-xs text-muted-foreground">{data?.step ?? "Procesando…"}</p>
          {total > 0 && (
            <>
              <div className="h-1.5 w-full rounded-full bg-white/5 overflow-hidden">
                <div
                  className="h-full bg-accent transition-all duration-500"
                  style={{ width: `${pct}%` }}
                />
              </div>
              <p className="text-[10px] text-muted-foreground tabular-nums">
                {current} / {total} ({pct}%)
              </p>
            </>
          )}
        </div>
      )}

      {!isRunning && result && (
        <div className="grid grid-cols-3 gap-2 text-[10px] text-muted-foreground">
          <div className="rounded border border-border/50 bg-white/[0.02] px-2 py-1.5">
            <div className="display-num text-foreground text-base tabular-nums">{result.ok ?? 0}</div>
            <div>descargadas</div>
          </div>
          <div className="rounded border border-border/50 bg-white/[0.02] px-2 py-1.5">
            <div className="display-num text-foreground text-base tabular-nums">{result.skip ?? 0}</div>
            <div>existentes</div>
          </div>
          <div className="rounded border border-border/50 bg-white/[0.02] px-2 py-1.5">
            <div className="display-num text-foreground text-base tabular-nums">
              {(result.not_found ?? 0) + (result.error ?? 0)}
            </div>
            <div>fallos</div>
          </div>
        </div>
      )}

      <button
        onClick={() => startMutation.mutate()}
        disabled={busy}
        className="w-full inline-flex items-center justify-center gap-2 px-3 py-2 rounded-md text-sm font-semibold bg-white/5 text-foreground border border-border hover:bg-white/10 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {busy ? (
          <>
            <Loader2 className="h-4 w-4 animate-spin" />
            Descargando…
          </>
        ) : (
          <>
            <ImageIcon className="h-4 w-4" />
            Descargar fotos pendientes
          </>
        )}
      </button>
    </motion.div>
  );
}
