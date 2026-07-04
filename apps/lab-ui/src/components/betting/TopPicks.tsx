import { motion } from "framer-motion";
import type { StrategyResult } from "../../api/client";

interface TopPicksProps {
  strategies: Record<string, StrategyResult>;
}

interface PickStat {
  name: string;
  appearances: number;
  hits: number;
  hitRate: number;
}

export function TopPicks({ strategies }: TopPicksProps) {
  const pickMap = new Map<string, { appearances: number; hits: number }>();

  const sourceStrat =
    strategies["singles"] ??
    strategies["doubles"] ??
    strategies["triples"] ??
    Object.values(strategies)[0];
  if (sourceStrat) {
    for (const ev of sourceStrat.events) {
      for (const p of ev.picks) {
        const entry = pickMap.get(p.pick) || { appearances: 0, hits: 0 };
        entry.appearances++;
        if (p.hit === true) entry.hits++;
        pickMap.set(p.pick, entry);
      }
    }
  }

  const picks: PickStat[] = Array.from(pickMap.entries())
    .map(([name, s]) => ({
      name,
      appearances: s.appearances,
      hits: s.hits,
      hitRate: s.appearances > 0 ? s.hits / s.appearances : 0,
    }))
    .sort((a, b) => b.hits - a.hits || b.hitRate - a.hitRate)
    .slice(0, 15);

  const maxAppearances = Math.max(...picks.map((p) => p.appearances), 1);

  return (
    <div className="bg-card border border-border rounded-xl p-5">
      <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-widest mb-4">
        Top Picks
      </h3>
      <div className="space-y-1.5">
        {picks.map((p, i) => (
          <motion.div
            key={p.name}
            initial={{ opacity: 0, x: -10 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: i * 0.03 }}
            className="flex items-center gap-3 text-xs"
          >
            <span className="w-5 text-right text-border tabular-nums">
              {i + 1}
            </span>
            <span className="w-[140px] truncate text-foreground font-medium">
              {p.name}
            </span>
            <div className="flex-1 h-4 bg-border/20 rounded overflow-hidden">
              <motion.div
                initial={{ width: 0 }}
                animate={{
                  width: `${(p.appearances / maxAppearances) * 100}%`,
                }}
                transition={{ duration: 0.4, delay: i * 0.03 }}
                className={`h-full rounded ${
                  p.hitRate >= 0.8
                    ? "bg-success/60"
                    : p.hitRate >= 0.5
                    ? "bg-warning/60"
                    : "bg-destructive/60"
                }`}
              />
            </div>
            <span className="w-12 text-right tabular-nums text-muted-foreground">
              {(p.hitRate * 100).toFixed(0)}%
            </span>
            <span className="w-8 text-right tabular-nums text-border">
              {p.appearances}x
            </span>
          </motion.div>
        ))}
        {picks.length === 0 && (
          <div className="text-xs text-muted-foreground text-center py-4">
            Sin datos de picks
          </div>
        )}
      </div>
    </div>
  );
}
