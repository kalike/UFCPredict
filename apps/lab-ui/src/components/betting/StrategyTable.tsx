import type { StrategyResult } from "../../api/client";

const RISK_BADGE: Record<string, { label: string; cls: string }> = {
  singles: { label: "Bajo", cls: "bg-success/15 text-success" },
  doubles: { label: "Medio", cls: "bg-warning/15 text-warning" },
  triples: { label: "Alto", cls: "bg-destructive/15 text-destructive" },
  baseline: { label: "Ref.", cls: "bg-border/30 text-muted-foreground" },
};

function sharpeColor(s: number): string {
  if (s >= 0.5) return "text-success font-bold";
  if (s >= 0.25) return "text-success";
  if (s >= 0) return "text-warning";
  return "text-destructive font-semibold";
}

interface StrategyTableProps {
  strategies: Record<string, StrategyResult>;
  bestStrategy: string;
}

export function StrategyTable({ strategies, bestStrategy }: StrategyTableProps) {
  const keys = ["singles", "doubles", "triples", "baseline"].filter(
    (k) => strategies[k]
  );

  return (
    <div className="bg-card border border-border rounded-xl p-5">
      <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-widest mb-4">
        Comparativa de Estrategias
      </h3>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-muted-foreground text-xs uppercase tracking-wider">
              <th className="text-left py-2 px-3">Estrategia</th>
              <th className="text-right py-2 px-3">Bets</th>
              <th className="text-right py-2 px-3">Stake</th>
              <th className="text-right py-2 px-3">Return</th>
              <th className="text-right py-2 px-3">Profit</th>
              <th className="text-right py-2 px-3">ROI</th>
              <th className="text-right py-2 px-3">Win Rate</th>
              <th className="text-right py-2 px-3">Drawdown</th>
              <th className="text-right py-2 px-3">Sharpe</th>
            </tr>
          </thead>
          <tbody>
            {keys.map((key) => {
              const s = strategies[key];
              const isBest = key === bestStrategy;
              const badge = RISK_BADGE[key] || RISK_BADGE.baseline;
              return (
                <tr
                  key={key}
                  className={`border-b border-border/50 transition-colors hover:bg-border/20 ${
                    isBest ? "border-l-2 border-l-accent bg-accent/5" : ""
                  }`}
                >
                  <td className="py-3 px-3">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-foreground capitalize">
                        {key}
                      </span>
                      <span
                        className={`text-[10px] px-1.5 py-0.5 rounded font-semibold ${badge.cls}`}
                      >
                        {badge.label}
                      </span>
                    </div>
                  </td>
                  <td className="text-right py-3 px-3 tabular-nums text-foreground">
                    {s.total_bets}
                  </td>
                  <td className="text-right py-3 px-3 tabular-nums text-foreground">
                    ${s.total_stake.toFixed(0)}
                  </td>
                  <td className="text-right py-3 px-3 tabular-nums text-foreground">
                    ${s.total_return.toFixed(0)}
                  </td>
                  <td
                    className={`text-right py-3 px-3 tabular-nums font-semibold ${
                      s.profit >= 0 ? "text-success" : "text-destructive"
                    }`}
                  >
                    {s.profit >= 0 ? "+" : ""}${s.profit.toFixed(0)}
                  </td>
                  <td
                    className={`text-right py-3 px-3 tabular-nums font-semibold ${
                      s.roi_pct >= 0 ? "text-success" : "text-destructive"
                    }`}
                  >
                    {s.roi_pct >= 0 ? "+" : ""}
                    {s.roi_pct.toFixed(1)}%
                  </td>
                  <td className="text-right py-3 px-3 tabular-nums text-foreground">
                    {(s.hit_rate_parlays * 100).toFixed(1)}%
                  </td>
                  <td className="text-right py-3 px-3 tabular-nums text-warning">
                    ${Math.abs(s.max_drawdown).toFixed(0)}
                  </td>
                  <td
                    className={`text-right py-3 px-3 tabular-nums ${sharpeColor(s.sharpe_ratio)}`}
                  >
                    {s.sharpe_ratio.toFixed(2)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
