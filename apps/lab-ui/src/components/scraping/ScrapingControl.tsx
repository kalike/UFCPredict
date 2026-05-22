import { useState } from "react";
import { motion } from "framer-motion";
import { Loader2, Play, ChevronDown } from "lucide-react";
import { fmtDate } from "../../lib/formatters";
import {
  deriveStatus,
  useScrapingStatus,
  useStartScraping,
} from "./useScraping";
import { StatusBadge } from "./StatusBadge";

export function ScrapingControl() {
  const { data } = useScrapingStatus();
  const startMutation = useStartScraping();
  const [letters, setLetters] = useState("");
  const [showAdvanced, setShowAdvanced] = useState(false);

  const status = deriveStatus(data);
  const isRunning = status === "running";
  const lastRun = data?.finished_at ?? data?.started_at;
  const busy = isRunning || startMutation.isPending;

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
      className="rounded-lg border border-border bg-card p-5 space-y-4"
    >
      <div className="flex items-center justify-between gap-4">
        <div className="space-y-1">
          <h2 className="text-foreground font-semibold text-base">Control de Scraping</h2>
          <p className="text-muted-foreground text-xs">UFCStats incremental · ingesta DB · Tapology</p>
          {lastRun && (
            <p className="text-muted-foreground text-xs">
              Última ejecución: {fmtDate(lastRun)}
            </p>
          )}
        </div>
        <StatusBadge status={status} />
      </div>

      {data?.error && (
        <p className="text-destructive text-sm rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 break-words">
          {data.error}
        </p>
      )}

      {/* Advanced: optional letter subset (lab-api capability for quick runs) */}
      <div className="space-y-2">
        <button
          type="button"
          onClick={() => setShowAdvanced((v) => !v)}
          className="flex items-center gap-1 text-[11px] uppercase tracking-widest text-muted-foreground hover:text-foreground transition-colors"
        >
          <ChevronDown
            className={`h-3.5 w-3.5 transition-transform ${showAdvanced ? "rotate-180" : ""}`}
          />
          Avanzado
        </button>
        {showAdvanced && (
          <input
            value={letters}
            onChange={(e) => setLetters(e.target.value)}
            placeholder="letras (opcional, ej. a,b,c)"
            disabled={busy}
            className="w-full bg-background border border-border rounded-md px-3 py-1.5 text-sm font-mono focus:border-accent focus:outline-none disabled:opacity-50"
          />
        )}
      </div>

      <button
        onClick={() => startMutation.mutate(letters.trim() || undefined)}
        disabled={busy}
        className="w-full inline-flex items-center justify-center gap-2 px-3 py-2 rounded-md text-sm font-semibold bg-accent text-accent-foreground shadow-[var(--shadow-primary-btn)] hover:bg-accent-hi transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {busy ? (
          <>
            <Loader2 className="h-4 w-4 animate-spin" />
            Ejecutando…
          </>
        ) : (
          <>
            <Play className="h-4 w-4" />
            Iniciar Scraping
          </>
        )}
      </button>
    </motion.div>
  );
}
