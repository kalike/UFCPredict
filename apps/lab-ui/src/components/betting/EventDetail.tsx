import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ChevronDown, Check, X } from "lucide-react";
import type { StrategyResult, EventBacktestDetail } from "../../api/client";

interface EventDetailProps {
  strategies: Record<string, StrategyResult>;
}

const COMBO_BADGE: Record<string, string> = {
  double: "bg-info/15 text-info",
  triple: "bg-accent-2/15 text-accent-2",
};

function CombosTable({
  combos,
}: {
  combos: EventBacktestDetail["combos"];
}) {
  const hitCount = combos.filter((c) => c.hit === true).length;
  const resolvedCount = combos.filter((c) => c.hit !== null).length;
  const totalStake = combos.reduce((s, c) => s + c.stake, 0);
  const totalReturn = combos
    .filter((c) => c.hit === true)
    .reduce((s, c) => s + c.potential_return, 0);
  const profit = totalReturn - totalStake;

  return (
    <div>
      <div className="flex gap-4 text-[10px] text-muted-foreground mb-2 px-2">
        <span>
          Acertados:{" "}
          <span className="text-foreground font-semibold">
            {hitCount}/{resolvedCount}
          </span>
        </span>
        <span>
          Stake:{" "}
          <span className="text-foreground font-semibold">
            ${totalStake.toFixed(0)}
          </span>
        </span>
        <span>
          P&L:{" "}
          <span
            className={`font-semibold ${
              profit >= 0 ? "text-success" : "text-destructive"
            }`}
          >
            {profit >= 0 ? "+" : ""}${profit.toFixed(0)}
          </span>
        </span>
      </div>

      <table className="w-full text-xs">
        <thead>
          <tr className="text-muted-foreground border-b border-border/30 uppercase tracking-wider">
            <th className="text-left py-1.5 px-2">Picks</th>
            <th className="text-right py-1.5 px-2">Odds</th>
            <th className="text-right py-1.5 px-2">Prob</th>
            <th className="text-right py-1.5 px-2">EV</th>
            <th className="text-right py-1.5 px-2">Stake</th>
            <th className="text-right py-1.5 px-2">Return</th>
            <th className="text-center py-1.5 px-2">Hit</th>
          </tr>
        </thead>
        <tbody>
          {combos.map((c, j) => {
            const badge = COMBO_BADGE[c.type] || "";
            return (
              <tr key={j} className="border-b border-border/20">
                <td className="py-1.5 px-2">
                  <div className="flex items-center gap-1.5 flex-wrap">
                    {c.pick_names.map((name, k) => (
                      <span
                        key={k}
                        className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${badge}`}
                      >
                        {name}
                      </span>
                    ))}
                  </div>
                </td>
                <td className="text-right py-1.5 px-2 tabular-nums text-foreground">
                  {c.combined_odds.toFixed(2)}
                </td>
                <td className="text-right py-1.5 px-2 tabular-nums text-muted-foreground">
                  {(c.combined_prob * 100).toFixed(0)}%
                </td>
                <td
                  className={`text-right py-1.5 px-2 tabular-nums ${
                    c.ev >= 0 ? "text-success" : "text-destructive"
                  }`}
                >
                  {c.ev >= 0 ? "+" : ""}
                  {c.ev.toFixed(3)}
                </td>
                <td className="text-right py-1.5 px-2 tabular-nums text-foreground">
                  ${c.stake.toFixed(0)}
                </td>
                <td className="text-right py-1.5 px-2 tabular-nums text-muted-foreground">
                  ${c.potential_return.toFixed(0)}
                </td>
                <td className="text-center py-1.5 px-2">
                  {c.hit === true && (
                    <Check size={14} className="inline text-success" />
                  )}
                  {c.hit === false && (
                    <X size={14} className="inline text-destructive" />
                  )}
                  {c.hit === null && (
                    <span className="text-border">-</span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function EventRow({
  event,
  strategies,
  index,
}: {
  event: EventBacktestDetail;
  strategies: Record<string, StrategyResult>;
  index: number;
}) {
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState<"picks" | "doubles" | "triples">("picks");

  const totalProfit = ["singles", "doubles", "triples"].reduce((sum, key) => {
    return sum + (strategies[key]?.events[index]?.profit || 0);
  }, 0);
  const totalStake = ["singles", "doubles", "triples"].reduce((sum, key) => {
    return sum + (strategies[key]?.events[index]?.stake || 0);
  }, 0);
  const totalBets = ["singles", "doubles", "triples"].reduce((sum, key) => {
    return sum + (strategies[key]?.events[index]?.n_bets || 0);
  }, 0);
  const roi = totalStake > 0 ? (totalProfit / totalStake) * 100 : 0;

  const doublesEvent = strategies.doubles?.events[index];
  const triplesEvent = strategies.triples?.events[index];
  const doubleCombos = doublesEvent?.combos || [];
  const tripleCombos = triplesEvent?.combos || [];

  return (
    <div className="border-b border-border/30">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-3 py-3 px-3 text-xs hover:bg-border/10 transition-colors"
      >
        <ChevronDown
          size={14}
          className={`text-muted-foreground transition-transform ${
            open ? "rotate-180" : ""
          }`}
        />
        <span className="flex-1 text-left text-foreground font-medium truncate">
          {event.event_name}
        </span>
        <span className="w-20 text-muted-foreground">{event.date}</span>
        <span className="w-12 text-right tabular-nums text-foreground">
          {event.n_qualified}
        </span>
        <span className="w-14 text-right tabular-nums text-foreground">
          {totalBets}
        </span>
        <span className="w-16 text-right tabular-nums text-foreground">
          ${totalStake.toFixed(0)}
        </span>
        <span
          className={`w-16 text-right tabular-nums font-semibold ${
            totalProfit >= 0 ? "text-success" : "text-destructive"
          }`}
        >
          {totalProfit >= 0 ? "+" : ""}${totalProfit.toFixed(0)}
        </span>
        <span
          className={`w-16 text-right tabular-nums ${
            roi >= 0 ? "text-success" : "text-destructive"
          }`}
        >
          {roi >= 0 ? "+" : ""}
          {roi.toFixed(0)}%
        </span>
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="px-6 pb-4">
              <div className="flex gap-1 mb-3 border-b border-border/30">
                <button
                  onClick={() => setTab("picks")}
                  className={`px-3 py-1.5 text-xs font-semibold transition-colors border-b-2 -mb-px ${
                    tab === "picks"
                      ? "border-accent text-foreground"
                      : "border-transparent text-muted-foreground hover:text-foreground"
                  }`}
                >
                  Picks ({event.picks.length})
                </button>
                {doubleCombos.length > 0 && (
                  <button
                    onClick={() => setTab("doubles")}
                    className={`px-3 py-1.5 text-xs font-semibold transition-colors border-b-2 -mb-px ${
                      tab === "doubles"
                        ? "border-info text-foreground"
                        : "border-transparent text-muted-foreground hover:text-foreground"
                    }`}
                  >
                    Doubles ({doubleCombos.length})
                  </button>
                )}
                {tripleCombos.length > 0 && (
                  <button
                    onClick={() => setTab("triples")}
                    className={`px-3 py-1.5 text-xs font-semibold transition-colors border-b-2 -mb-px ${
                      tab === "triples"
                        ? "border-accent-2 text-foreground"
                        : "border-transparent text-muted-foreground hover:text-foreground"
                    }`}
                  >
                    Triples ({tripleCombos.length})
                  </button>
                )}
              </div>

              {tab === "picks" && (
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-muted-foreground border-b border-border/30 uppercase tracking-wider">
                      <th className="text-left py-1.5 px-2">Pick</th>
                      <th className="text-right py-1.5 px-2">Odds</th>
                      <th className="text-right py-1.5 px-2">Prob</th>
                      <th className="text-right py-1.5 px-2">Stake</th>
                      <th className="text-center py-1.5 px-2">Resultado</th>
                    </tr>
                  </thead>
                  <tbody>
                    {event.picks.map((p, j) => (
                      <tr key={j} className="border-b border-border/20">
                        <td className="py-1.5 px-2 text-foreground">
                          {p.pick}
                        </td>
                        <td className="text-right py-1.5 px-2 tabular-nums text-muted-foreground">
                          {p.odds.toFixed(2)}
                        </td>
                        <td className="text-right py-1.5 px-2 tabular-nums text-muted-foreground">
                          {(p.prob * 100).toFixed(0)}%
                        </td>
                        <td className="text-right py-1.5 px-2 tabular-nums text-foreground">
                          {p.stake != null ? (
                            `$${p.stake.toFixed(0)}`
                          ) : (
                            <span className="text-border">-</span>
                          )}
                        </td>
                        <td className="text-center py-1.5 px-2">
                          {p.hit === true && (
                            <Check size={14} className="inline text-success" />
                          )}
                          {p.hit === false && (
                            <X size={14} className="inline text-destructive" />
                          )}
                          {p.hit === null && (
                            <span className="text-border">-</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}

              {(tab === "doubles" || tab === "triples") && (
                <CombosTable
                  combos={tab === "doubles" ? doubleCombos : tripleCombos}
                />
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export function EventDetail({ strategies }: EventDetailProps) {
  const events = strategies.singles?.events || [];

  return (
    <div className="bg-card border border-border rounded-xl p-5">
      <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-widest mb-4">
        Detalle por Evento
      </h3>
      <div className="flex items-center gap-3 text-[10px] text-muted-foreground uppercase tracking-wider border-b border-border px-3 pb-2">
        <span className="w-[14px]" />
        <span className="flex-1">Evento</span>
        <span className="w-20">Fecha</span>
        <span className="w-12 text-right">Picks</span>
        <span className="w-14 text-right">Apuestas</span>
        <span className="w-16 text-right">Stake</span>
        <span className="w-16 text-right">Profit</span>
        <span className="w-16 text-right">ROI</span>
      </div>
      {events.map((ev, i) => (
        <EventRow key={i} event={ev} strategies={strategies} index={i} />
      ))}
      {events.length === 0 && (
        <div className="text-xs text-muted-foreground text-center py-8">
          No hay eventos para mostrar
        </div>
      )}
    </div>
  );
}
