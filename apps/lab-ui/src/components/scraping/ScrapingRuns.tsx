import { motion } from "framer-motion";
import type { ScrapingRun } from "../../api/client";
import { fmtDate } from "../../lib/formatters";

interface ScrapingRunsProps {
  runs: ScrapingRun[];
  isLoading: boolean;
}

function sourceBadge(source: string): string {
  if (source === "fotos") return "bg-info/15 text-info border-info/30";
  return "bg-accent/15 text-accent border-accent/30";
}

export function ScrapingRuns({ runs, isLoading }: ScrapingRunsProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay: 0.1 }}
      className="rounded-lg border border-border bg-card overflow-hidden"
    >
      <div className="px-5 py-4 border-b border-border">
        <h2 className="text-foreground font-semibold text-base">Runs recientes</h2>
      </div>

      {isLoading ? (
        <div className="px-5 py-10 text-center text-muted-foreground text-sm">Cargando…</div>
      ) : runs.length === 0 ? (
        <div className="px-5 py-10 text-center text-muted-foreground text-sm">
          No hay runs registrados
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-white/[0.02] text-[10px] uppercase tracking-widest text-muted-foreground">
                <th className="px-5 py-3 text-left font-semibold">ID</th>
                <th className="px-3 py-3 text-left font-semibold">Fuente</th>
                <th className="px-3 py-3 text-left font-semibold">Inicio</th>
                <th className="px-3 py-3 text-right font-semibold">Nuevos</th>
                <th className="px-3 py-3 text-right font-semibold">Actualizados</th>
                <th className="px-5 py-3 text-left font-semibold">Error</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/40">
              {runs.map((r) => (
                <tr key={r.id} className="hover:bg-white/[0.02] transition-colors">
                  <td className="px-5 py-2.5 font-mono text-xs text-muted-foreground">{r.id}</td>
                  <td className="px-3 py-2.5">
                    <span
                      className={`px-2 py-0.5 rounded text-[10px] uppercase tracking-widest font-semibold border ${sourceBadge(r.source)}`}
                    >
                      {r.source}
                    </span>
                  </td>
                  <td className="px-3 py-2.5 text-xs text-muted-foreground">{fmtDate(r.started_at)}</td>
                  <td className="px-3 py-2.5 text-right display-num text-sm text-success tabular-nums">
                    {r.new_count}
                  </td>
                  <td className="px-3 py-2.5 text-right display-num text-sm text-foreground tabular-nums">
                    {r.updated_count}
                  </td>
                  <td className="px-5 py-2.5 text-xs text-destructive max-w-[16rem] truncate" title={r.error_msg ?? ""}>
                    {r.error_msg ?? ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </motion.div>
  );
}
