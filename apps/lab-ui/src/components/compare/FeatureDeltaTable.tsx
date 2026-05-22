import { motion } from "framer-motion";
import type { FeatureDelta } from "../../api/client";

interface FeatureDeltaTableProps {
  deltas: FeatureDelta[];
  f1Name: string;
  f2Name: string;
}

function formatVal(v: number | null): string {
  if (v == null) return "—";
  // If value is in 0–1 range (rates/percentages), show as percentage
  if (v >= 0 && v <= 1) {
    return `${(v * 100).toFixed(1)}%`;
  }
  return v.toFixed(1);
}

export function FeatureDeltaTable({ deltas, f1Name, f2Name }: FeatureDeltaTableProps) {
  if (!deltas || deltas.length === 0) {
    return (
      <div className="bg-card border border-border rounded-xl p-5">
        <p className="text-muted-foreground text-sm text-center py-4">
          Sin datos de deltas disponibles
        </p>
      </div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay: 0.15 }}
      className="bg-card border border-border rounded-xl p-5 space-y-3"
    >
      <h3 className="text-muted-foreground text-xs uppercase tracking-widest font-semibold">
        Deltas de características
      </h3>

      <div className="max-h-80 overflow-y-auto rounded-lg border border-border/40">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-card z-10">
            <tr className="border-b border-border/40">
              <th className="text-left px-3 py-2 text-[10px] uppercase tracking-widest text-muted-foreground font-semibold">
                Estadística
              </th>
              <th className="text-right px-3 py-2 text-[10px] uppercase tracking-widest text-accent font-semibold">
                {f1Name.split(" ")[0]}
              </th>
              <th className="text-right px-3 py-2 text-[10px] uppercase tracking-widest text-info font-semibold">
                {f2Name.split(" ")[0]}
              </th>
              <th className="text-center px-3 py-2 text-[10px] uppercase tracking-widest text-muted-foreground font-semibold">
                Ventaja
              </th>
            </tr>
          </thead>
          <tbody>
            {deltas.map((delta, i) => {
              const f1Better = delta.better === "fighter_1";
              const f2Better = delta.better === "fighter_2";
              const equal = !f1Better && !f2Better;

              return (
                <tr
                  key={delta.feature}
                  className={`border-b border-border/20 last:border-0 transition-colors hover:bg-card-hover ${
                    i % 2 === 0 ? "" : "bg-background/30"
                  }`}
                >
                  <td className="px-3 py-2 text-foreground text-xs font-medium">
                    {delta.label}
                  </td>
                  <td
                    className={`px-3 py-2 text-right text-xs tabular-nums ${
                      f1Better ? "text-accent font-semibold" : "text-muted"
                    }`}
                  >
                    {formatVal(delta.f1_value)}
                  </td>
                  <td
                    className={`px-3 py-2 text-right text-xs tabular-nums ${
                      f2Better ? "text-info font-semibold" : "text-muted"
                    }`}
                  >
                    {formatVal(delta.f2_value)}
                  </td>
                  <td className="px-3 py-2 text-center">
                    {equal ? (
                      <span className="text-muted-foreground text-xs">—</span>
                    ) : f1Better ? (
                      <span className="text-accent text-xs font-bold">→</span>
                    ) : (
                      <span className="text-info text-xs font-bold">←</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </motion.div>
  );
}
