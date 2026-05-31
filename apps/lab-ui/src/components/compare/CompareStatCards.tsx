import { motion } from "framer-motion";
import type { CompareByNameResponse } from "../../api/client";
import { fmtPct } from "../../lib/formatters";

interface CompareStatCardsProps {
  data: CompareByNameResponse;
}

const STAT_KEYS: { key: string; label: string; format: "pct" | "number" }[] = [
  { key: "win_rate",          label: "Win Rate",    format: "pct"    },
  { key: "ko_rate",           label: "KO Rate",     format: "pct"    },
  { key: "sig_str_accuracy",  label: "Sig Str Acc", format: "pct"    },
  { key: "td_accuracy",       label: "TD Accuracy", format: "pct"    },
  { key: "elo",               label: "ELO Rating",  format: "number" },
  { key: "n_fights",          label: "Peleas",      format: "number" },
];

function formatValue(val: number, format: "pct" | "number"): string {
  if (val == null) return "—";
  if (format === "pct") return fmtPct(val);
  return Math.round(val).toString();
}

export function CompareStatCards({ data }: CompareStatCardsProps) {
  const { stat_comparison, fighter_1, fighter_2 } = data;

  return (
    <div className="bg-card border border-border rounded-xl p-5 space-y-4">
      <h3 className="text-muted-foreground text-xs uppercase tracking-widest font-semibold">
        Estadísticas clave
      </h3>
      <div className="grid grid-cols-3 gap-3">
        {STAT_KEYS.map(({ key, label, format }, idx) => {
          const stat = stat_comparison[key];
          if (!stat) return null;

          const f1Better = stat.better === "fighter_1";
          const f2Better = stat.better === "fighter_2";

          return (
            <motion.div
              key={key}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.35, delay: idx * 0.06 }}
              className="bg-background border border-border/40 rounded-xl p-3 flex flex-col gap-2 card-hover-glow"
            >
              <p className="text-[10px] uppercase tracking-widest text-muted-foreground font-semibold">
                {label}
              </p>

              {/* Fighter 1 row */}
              <div className="flex items-baseline justify-between gap-1">
                <span
                  className={`font-bold leading-none ${f1Better ? "text-accent" : "text-foreground"}`}
                  style={{ fontFamily: "'Oswald', sans-serif", fontSize: "1.1rem" }}
                >
                  {formatValue(stat.f1_value, format)}
                </span>
                <span className="text-[9px] text-muted-foreground truncate text-right">
                  {fighter_1.name.split(" ")[0]}
                  {f1Better && <span className="text-accent ml-0.5">↑</span>}
                </span>
              </div>

              <div className="h-px bg-border/30" />

              {/* Fighter 2 row */}
              <div className="flex items-baseline justify-between gap-1">
                <span
                  className={`font-bold leading-none ${f2Better ? "text-info" : "text-foreground"}`}
                  style={{ fontFamily: "'Oswald', sans-serif", fontSize: "1.1rem" }}
                >
                  {formatValue(stat.f2_value, format)}
                </span>
                <span className="text-[9px] text-muted-foreground truncate text-right">
                  {fighter_2.name.split(" ")[0]}
                  {f2Better && <span className="text-info ml-0.5">↑</span>}
                </span>
              </div>
            </motion.div>
          );
        })}
      </div>
    </div>
  );
}
