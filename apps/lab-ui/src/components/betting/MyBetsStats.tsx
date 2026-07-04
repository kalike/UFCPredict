import type { UserBetsStats } from "../../api/client";
import { Card } from "../ui";

function Kpi({
  label,
  value,
  hint,
  tone,
}: {
  label: string;
  value: string;
  hint?: string;
  tone?: "pos" | "neg";
}) {
  const toneCls =
    tone === "pos" ? "text-emerald-400" : tone === "neg" ? "text-red-400" : "text-foreground";
  return (
    <Card>
      <div className="text-[10px] uppercase tracking-widest text-muted-foreground mb-1">{label}</div>
      <div className={`text-xl font-semibold tabular-nums ${toneCls}`}>{value}</div>
      {hint && <div className="text-xs text-muted-foreground mt-1">{hint}</div>}
    </Card>
  );
}

const fmt = (n: number, d = 2) => n.toFixed(d);

export function MyBetsStats({ stats }: { stats: UserBetsStats }) {
  const ec = stats.engine_comparison;
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <Kpi
          label="P&L neto"
          value={`${stats.net_profit >= 0 ? "+" : ""}${fmt(stats.net_profit, 0)}€`}
          hint={`Stake ${fmt(stats.total_stake, 0)}€ · Return ${fmt(stats.total_returned, 0)}€`}
          tone={stats.net_profit >= 0 ? "pos" : "neg"}
        />
        <Kpi
          label="ROI"
          value={`${stats.roi_pct >= 0 ? "+" : ""}${fmt(stats.roi_pct, 1)}%`}
          tone={stats.roi_pct >= 0 ? "pos" : "neg"}
        />
        <Kpi
          label="Winrate"
          value={`${fmt(stats.winrate * 100, 1)}%`}
          hint={`${stats.n_won} / ${stats.n_settled} resueltas`}
        />
        <Kpi
          label="Apuestas"
          value={`${stats.n_bets}`}
          hint={`${stats.n_bets - stats.n_settled} pendientes`}
        />
        <Kpi
          label="Δ vs Engine"
          value={`${ec.delta_roi_pct >= 0 ? "+" : ""}${fmt(ec.delta_roi_pct, 1)}%`}
          hint={`Engine ROI ${fmt(ec.engine_roi_pct, 1)}%`}
          tone={ec.delta_roi_pct >= 0 ? "pos" : "neg"}
        />
      </div>

      {stats.by_type.length > 0 && (
        <Card>
          <div className="text-xs uppercase tracking-widest text-muted-foreground mb-3">
            Desglose por tipo
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {stats.by_type.map((b) => (
              <div key={b.bet_type} className="bg-white/5 rounded-lg p-3 text-xs space-y-1">
                <div className="flex items-center justify-between">
                  <span className="font-semibold uppercase">{b.bet_type}</span>
                  <span className="text-muted-foreground">{b.n_bets} bets</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">ROI</span>
                  <span
                    className={`tabular-nums ${b.roi_pct >= 0 ? "text-emerald-400" : "text-red-400"}`}
                  >
                    {b.roi_pct >= 0 ? "+" : ""}
                    {fmt(b.roi_pct, 1)}%
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Winrate</span>
                  <span className="tabular-nums">{fmt(b.winrate * 100, 1)}%</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Profit</span>
                  <span
                    className={`tabular-nums ${b.profit >= 0 ? "text-emerald-400" : "text-red-400"}`}
                  >
                    {b.profit >= 0 ? "+" : ""}
                    {fmt(b.profit, 0)}€
                  </span>
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}
