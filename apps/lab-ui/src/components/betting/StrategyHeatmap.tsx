import type { StrategyResult } from "../../api/client";

interface StrategyHeatmapProps {
  strategies: Record<string, StrategyResult>;
}

function roiColor(roi: number): string {
  if (roi > 30) return "bg-success/40 text-success";
  if (roi > 10) return "bg-success/20 text-success";
  if (roi > 0) return "bg-success/10 text-success";
  if (roi > -10) return "bg-destructive/10 text-destructive";
  if (roi > -30) return "bg-destructive/20 text-destructive";
  return "bg-destructive/40 text-destructive";
}

export function StrategyHeatmap({ strategies }: StrategyHeatmapProps) {
  const stratKeys = ["singles", "doubles", "triples"].filter(
    (k) => strategies[k]
  );
  const events = strategies.singles?.events || [];

  return (
    <div className="bg-card border border-border rounded-xl p-5">
      <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-widest mb-4">
        Heatmap Evento x Estrategia
      </h3>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-border text-muted-foreground uppercase tracking-wider">
              <th className="text-left py-2 px-2">Evento</th>
              {stratKeys.map((k) => (
                <th key={k} className="text-center py-2 px-2 capitalize">
                  {k}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {events.map((ev, i) => (
              <tr key={i} className="border-b border-border/30">
                <td className="py-2 px-2 text-muted-foreground truncate max-w-[180px]">
                  {ev.event_name}
                </td>
                {stratKeys.map((k) => {
                  const stratEvent = strategies[k]?.events[i];
                  if (!stratEvent || stratEvent.stake === 0) {
                    return (
                      <td key={k} className="py-2 px-2 text-center text-border">
                        -
                      </td>
                    );
                  }
                  const roi = (stratEvent.profit / stratEvent.stake) * 100;
                  return (
                    <td key={k} className="py-2 px-2 text-center">
                      <span
                        className={`inline-block px-2 py-1 rounded text-[11px] font-semibold tabular-nums ${roiColor(roi)}`}
                        title={`P&L: $${stratEvent.profit.toFixed(0)} | Bets: ${stratEvent.n_bets} | HR: ${(stratEvent.picks_hit_rate * 100).toFixed(0)}%`}
                      >
                        {roi >= 0 ? "+" : ""}
                        {roi.toFixed(0)}%
                      </span>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
