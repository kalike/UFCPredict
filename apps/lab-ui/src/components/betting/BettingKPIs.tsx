import { useState } from "react";
import { TrendingUp, DollarSign, Target, TrendingDown, BarChart3, Wallet, Dog, X, ArrowUpDown } from "lucide-react";
import type { StrategyResult } from "../../api/client";

const UNDERDOG_DECIMAL_THRESHOLD = 2.0;

const TYPE_LABEL: Record<string, string> = {
  singles: "Singles",
  doubles: "Doubles",
  triples: "Triples",
  baseline: "Baseline",
};

const BET_TYPES = ["singles", "doubles", "triples"] as const;
type BetType = (typeof BET_TYPES)[number];

type Leg = { pick: string; opponent: string | null };
type UnderdogBet = {
  event: string;
  legs: Leg[]; // the picked (underdog) fighter + opponent per leg
  odds: number; // decimal odds (single) or combined odds (parlay)
  stake: number;
  ret: number;
  profit: number;
  hit: boolean;
};

function underdogStats(
  strategy: StrategyResult,
  key: BetType,
): { total: number; hits: number; profit: number; bets: UnderdogBet[] } {
  const bets: UnderdogBet[] = [];
  for (const event of strategy.events) {
    const oddsByPick: Record<string, number> = {};
    const boutByPick: Record<string, { f1?: string; f2?: string }> = {};
    for (const p of event.picks) {
      oddsByPick[p.pick] = p.odds;
      boutByPick[p.pick] = { f1: p.fighter_1, f2: p.fighter_2 };
    }
    const legFor = (name: string): Leg => {
      const info = boutByPick[name];
      if (!info || !info.f1 || !info.f2) return { pick: name, opponent: null };
      const opp = name === info.f1 ? info.f2 : info.f1;
      return { pick: name, opponent: opp };
    };

    if (key === "singles") {
      for (const p of event.picks) {
        if (p.stake == null || p.hit == null) continue;
        if ((p.odds ?? 0) > UNDERDOG_DECIMAL_THRESHOLD) {
          const ret = p.hit ? p.stake * p.odds : 0;
          bets.push({
            event: event.event_name, legs: [legFor(p.pick)], odds: p.odds,
            stake: p.stake, ret, profit: ret - p.stake, hit: p.hit,
          });
        }
      }
    } else {
      for (const combo of event.combos ?? []) {
        if (combo.hit == null) continue;
        const hasDog = combo.pick_names.some((n) => (oddsByPick[n] ?? 0) > UNDERDOG_DECIMAL_THRESHOLD);
        if (hasDog) {
          const ret = combo.hit ? combo.potential_return : 0;
          bets.push({
            event: event.event_name, legs: combo.pick_names.map(legFor), odds: combo.combined_odds,
            stake: combo.stake, ret, profit: ret - combo.stake, hit: combo.hit,
          });
        }
      }
    }
  }
  const hits = bets.filter((b) => b.hit).length;
  const profit = bets.reduce((s, b) => s + b.profit, 0);
  return { total: bets.length, hits, profit, bets };
}

// Sharpe color tiers calibrated for per-event UFC betting backtests.
function sharpeColor(s: number): string {
  if (s >= 0.5) return "text-emerald-400";
  if (s >= 0.25) return "text-emerald-400/80";
  if (s >= 0) return "text-amber-400";
  return "text-red-400";
}
function sharpeLabel(s: number): string {
  if (s >= 0.5) return "fuerte";
  if (s >= 0.25) return "decente";
  if (s >= 0) return "débil";
  return "negativo";
}

function KPICard({
  label,
  value,
  subtitle,
  color,
  icon: Icon,
}: {
  label: string;
  value: string;
  subtitle?: string;
  color: string;
  icon: React.ElementType;
}) {
  return (
    <div className="bg-card border border-border rounded-lg p-5 hover:border-accent/30 transition-colors">
      <div className="flex items-start justify-between mb-3">
        <span className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
          {label}
        </span>
        <Icon size={16} className="text-muted-foreground/40" />
      </div>
      <div className={`font-display text-3xl leading-none tabular-nums mb-1.5 ${color}`}>{value}</div>
      {subtitle && <div className="text-xs text-muted-foreground">{subtitle}</div>}
    </div>
  );
}

function UnderdogBetsModal({
  title,
  bets,
  onClose,
}: {
  title: string;
  bets: UnderdogBet[];
  onClose: () => void;
}) {
  const [sort, setSort] = useState<{ key: "odds" | "profit"; dir: "asc" | "desc" }>({
    key: "odds",
    dir: "desc",
  });
  const toggleSort = (key: "odds" | "profit") =>
    setSort((s) => (s.key === key ? { key, dir: s.dir === "desc" ? "asc" : "desc" } : { key, dir: "desc" }));
  const sortArrow = (key: "odds" | "profit") => (sort.key === key ? (sort.dir === "desc" ? "↓" : "↑") : "");
  const sorted = [...bets].sort((a, b) => {
    const diff = a[sort.key] - b[sort.key];
    return sort.dir === "desc" ? -diff : diff;
  });
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      <div
        className="w-full max-w-2xl max-h-[80vh] flex flex-col rounded-lg border border-border bg-card"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 py-4 border-b border-border">
          <h3 className="text-sm font-semibold uppercase tracking-widest flex items-center gap-1.5">
            <Dog size={14} className="text-muted-foreground/60" /> {title} · {bets.length} apuestas
          </h3>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <X size={18} />
          </button>
        </div>
        <div className="overflow-y-auto">
          <table className="w-full text-xs">
            <thead className="text-muted-foreground sticky top-0 bg-card">
              <tr className="border-b border-border">
                <th className="text-left p-2 pl-5">Evento</th>
                <th className="text-left p-2">Combate</th>
                <th
                  className="text-right p-2 cursor-pointer select-none hover:text-foreground"
                  onClick={() => toggleSort("odds")}
                  title="Ordenar por cuota"
                >
                  <span className="inline-flex items-center gap-1">
                    Cuota <ArrowUpDown size={11} /> {sortArrow("odds")}
                  </span>
                </th>
                <th className="text-right p-2">Stake</th>
                <th className="text-right p-2">Return</th>
                <th
                  className="text-right p-2 cursor-pointer select-none hover:text-foreground"
                  onClick={() => toggleSort("profit")}
                  title="Ordenar por P&L"
                >
                  <span className="inline-flex items-center gap-1">
                    P&amp;L <ArrowUpDown size={11} /> {sortArrow("profit")}
                  </span>
                </th>
                <th className="text-left p-2 pr-5">Estado</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((b, i) => (
                <tr key={i} className="border-b border-border/40 hover:bg-white/5">
                  <td className="p-2 pl-5 text-foreground">{b.event || "—"}</td>
                  <td className="p-2">
                    {b.legs.map((leg, k) => (
                      <div key={k} className="whitespace-nowrap">
                        <span className="text-accent font-semibold">{leg.pick}</span>
                        {leg.opponent && <span className="text-muted-foreground"> vs {leg.opponent}</span>}
                      </div>
                    ))}
                  </td>
                  <td className="p-2 text-right tabular-nums text-foreground">{b.odds.toFixed(2)}</td>
                  <td className="p-2 text-right tabular-nums">${b.stake.toFixed(0)}</td>
                  <td className="p-2 text-right tabular-nums">${b.ret.toFixed(0)}</td>
                  <td
                    className={`p-2 text-right tabular-nums font-semibold ${
                      b.profit > 0 ? "text-emerald-400" : b.profit < 0 ? "text-red-400" : ""
                    }`}
                  >
                    {b.profit >= 0 ? "+" : ""}
                    {b.profit.toFixed(0)}€
                  </td>
                  <td className="p-2 pr-5">
                    <span
                      className={`px-2 py-0.5 rounded text-[10px] uppercase font-semibold ${
                        b.hit ? "bg-emerald-500/15 text-emerald-400" : "bg-red-500/15 text-red-400"
                      }`}
                    >
                      {b.hit ? "ganada" : "perdida"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function UnderdogCard({ s, betKey }: { s: StrategyResult; betKey: BetType }) {
  const [open, setOpen] = useState(false);
  const { total, hits, profit, bets } = underdogStats(s, betKey);
  const pct = total > 0 ? (hits / total) * 100 : 0;
  const color =
    total === 0 ? "text-muted-foreground" : pct >= 50 ? "text-emerald-400" : pct >= 33 ? "text-amber-400" : "text-red-400";
  const profitColor = profit > 0 ? "text-emerald-400" : profit < 0 ? "text-red-400" : "text-muted-foreground";
  const participationLabel = betKey === "singles" ? "picks underdog" : `${TYPE_LABEL[betKey].toLowerCase()} con underdog`;
  return (
    <>
      <div
        onClick={() => total > 0 && setOpen(true)}
        className={`bg-card border border-border rounded-lg px-4 py-3 flex items-center justify-between transition-colors ${
          total > 0 ? "cursor-pointer hover:border-accent/50" : "hover:border-accent/30"
        }`}
        title={total > 0 ? "Ver apuestas underdog" : undefined}
      >
        <div>
          <div className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground mb-0.5 flex items-center gap-1.5">
            <Dog size={11} className="text-muted-foreground/40" />
            Hit rate underdogs {TYPE_LABEL[betKey]}
          </div>
          <div className="text-xs text-muted-foreground">
            {total > 0 ? (
              <>
                <span className="text-foreground">
                  {hits}/{total}
                </span>
                <span className="ml-1">{participationLabel}</span>
                {" · "}
                P&amp;L{" "}
                <span className={profitColor}>
                  {profit >= 0 ? "+" : ""}
                  {profit.toFixed(0)}€
                </span>
              </>
            ) : (
              <span>sin apuestas con underdog</span>
            )}
          </div>
        </div>
        <div className="flex flex-col items-end">
          <div className={`font-display text-2xl leading-none tabular-nums ${color}`}>
            {total > 0 ? `${pct.toFixed(1)}%` : "—"}
          </div>
          <div className={`text-[10px] ${color}`}>
            {total === 0 ? "n/a" : pct >= 50 ? "fuerte" : pct >= 33 ? "decente" : "débil"}
          </div>
        </div>
      </div>
      {open && (
        <UnderdogBetsModal
          title={`Underdogs ${TYPE_LABEL[betKey]}`}
          bets={bets}
          onClose={() => setOpen(false)}
        />
      )}
    </>
  );
}

function SharpeByTypeCard({ s, betKey }: { s: StrategyResult; betKey: BetType }) {
  const sr = s.sharpe_ratio;
  const roi = s.total_stake > 0 ? ((s.total_return - s.total_stake) / s.total_stake) * 100 : 0;
  const hits = Math.round(s.hit_rate_parlays * s.total_bets);
  const hitPct = s.total_bets > 0 ? (hits / s.total_bets) * 100 : 0;
  return (
    <div className="bg-card border border-border rounded-lg px-4 py-3 flex items-center justify-between hover:border-accent/30 transition-colors">
      <div>
        <div className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground mb-0.5">
          Sharpe {TYPE_LABEL[betKey]}
        </div>
        <div className="text-xs text-muted-foreground">
          <span className="text-foreground">
            {hits}/{s.total_bets}
          </span>
          <span className="ml-1">({hitPct.toFixed(1)}%)</span> · ROI{" "}
          <span className={roi >= 0 ? "text-emerald-400" : "text-red-400"}>
            {roi >= 0 ? "+" : ""}
            {roi.toFixed(1)}%
          </span>{" "}
          · DD <span className="text-foreground">${Math.abs(s.max_drawdown).toFixed(0)}</span>
        </div>
      </div>
      <div className="flex flex-col items-end">
        <div className={`font-display text-2xl leading-none tabular-nums ${sharpeColor(sr)}`}>{sr.toFixed(2)}</div>
        <div className={`text-[10px] ${sharpeColor(sr)}`}>{sharpeLabel(sr)}</div>
      </div>
    </div>
  );
}

function MainCards({
  sr,
  totalEvents,
  subtitleStake,
  subtitleRoi,
  subtitleProfit,
}: {
  sr: StrategyResult;
  totalEvents: number;
  subtitleStake: string;
  subtitleRoi: string;
  subtitleProfit: string;
}) {
  const roiPct = sr.roi_pct;
  const profit = sr.profit;
  const totalBets = sr.total_bets;
  const totalHits = Math.round(sr.hit_rate_parlays * totalBets);
  const winRate = totalBets > 0 ? totalHits / totalBets : 0;
  const maxDd = sr.max_drawdown;
  const sharpe = sr.sharpe_ratio;

  const roiColor = roiPct >= 0 ? "text-emerald-400" : "text-red-400";
  const profitColor = profit >= 0 ? "text-emerald-400" : "text-red-400";
  const ddColor = Math.abs(maxDd) > sr.total_stake * 0.05 ? "text-amber-400" : "text-muted-foreground";

  void totalEvents;
  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
      <KPICard label="ROI Total" value={`${roiPct >= 0 ? "+" : ""}${roiPct.toFixed(1)}%`} subtitle={subtitleRoi} color={roiColor} icon={TrendingUp} />
      <KPICard label="Total Apostado" value={`$${sr.total_stake.toFixed(0)}`} subtitle={subtitleStake} color="text-foreground" icon={Wallet} />
      <KPICard label="Profit Neto" value={`${profit >= 0 ? "+" : ""}$${Math.abs(profit).toFixed(0)}`} subtitle={subtitleProfit} color={profitColor} icon={DollarSign} />
      <KPICard label="Win Rate Parlays" value={`${(winRate * 100).toFixed(1)}%`} subtitle={`${totalHits}/${totalBets} apuestas`} color={winRate > 0.6 ? "text-emerald-400" : "text-foreground"} icon={Target} />
      <KPICard label="Max Drawdown" value={`$${Math.abs(maxDd).toFixed(0)}`} subtitle="peor racha" color={ddColor} icon={TrendingDown} />
      <KPICard label="Sharpe Ratio" value={sharpe.toFixed(2)} subtitle={sharpeLabel(sharpe)} color={sharpeColor(sharpe)} icon={BarChart3} />
    </div>
  );
}

type Props = {
  strategies: Record<string, StrategyResult>;
  total: StrategyResult | null | undefined;
  totalEvents: number;
  strategy: string;
};

export function BettingKPIs({ strategies, total, totalEvents, strategy }: Props) {
  const present = BET_TYPES.filter((k) => strategies[k]);

  if (strategy === "total") {
    const t = total ?? strategies.singles;
    if (!t) return null;
    const baseline = strategies.baseline;
    const baselineRoi =
      baseline && baseline.total_stake > 0
        ? ((baseline.total_return - baseline.total_stake) / baseline.total_stake) * 100
        : null;
    const baselineDiff = baselineRoi != null ? (t.roi_pct - baselineRoi).toFixed(1) : null;
    return (
      <div className="space-y-4">
        <MainCards
          sr={t}
          totalEvents={totalEvents}
          subtitleRoi={baselineDiff != null ? `vs baseline ${Number(baselineDiff) >= 0 ? "+" : ""}${baselineDiff}%` : `${totalEvents} eventos`}
          subtitleStake={`${t.total_bets} apuestas · ${totalEvents} eventos`}
          subtitleProfit={`${present.length} estrategias`}
        />
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {present.map((k) => (
            <SharpeByTypeCard key={k} s={strategies[k]} betKey={k} />
          ))}
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {present.map((k) => (
            <UnderdogCard key={`ud-${k}`} s={strategies[k]} betKey={k} />
          ))}
        </div>
      </div>
    );
  }

  // Single strategy (singles/doubles/triples/baseline)
  const sr = strategies[strategy];
  if (!sr) return null;
  const isBetType = (BET_TYPES as readonly string[]).includes(strategy);
  return (
    <div className="space-y-4">
      <MainCards
        sr={sr}
        totalEvents={totalEvents}
        subtitleRoi={`${totalEvents} eventos`}
        subtitleStake={`${sr.total_bets} apuestas · ${totalEvents} eventos`}
        subtitleProfit={TYPE_LABEL[strategy] ?? strategy}
      />
      {isBetType && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <SharpeByTypeCard s={sr} betKey={strategy as BetType} />
          <UnderdogCard s={sr} betKey={strategy as BetType} />
        </div>
      )}
    </div>
  );
}
