import { motion } from "framer-motion";
import type { FightStatsRecord } from "../../api/client";
import { fmtDate } from "../../lib/formatters";

interface FightHistoryTableProps {
  history: FightStatsRecord[];
  fighterName: string;
  onSelectFight: (fightIndex: number) => void;
}

interface ResultBadgeProps {
  result: string;
}

function ResultBadge({ result }: ResultBadgeProps) {
  const upper = result.toUpperCase();
  let classes = "inline-flex items-center justify-center w-8 h-6 rounded text-[10px] font-bold tracking-wide";
  if (upper.startsWith("W")) {
    classes += " bg-success/10 text-success border border-success/20";
  } else if (upper.startsWith("L")) {
    classes += " bg-destructive/10 text-destructive border border-destructive/20";
  } else {
    classes += " bg-border text-muted border border-border";
  }
  const label = upper.startsWith("W") ? "W" : upper.startsWith("L") ? "L" : upper.startsWith("D") ? "D" : "NC";
  return <span className={classes}>{label}</span>;
}

export function FightHistoryTable({
  history,
  onSelectFight,
}: FightHistoryTableProps) {
  const sorted = [...history].sort((a, b) => b.fight_index - a.fight_index);

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay: 0.3 }}
      className="bg-card border border-border rounded-xl p-5"
    >
      <h3
        className="text-foreground text-sm font-semibold mb-4"
        style={{ fontFamily: "'Oswald', sans-serif" }}
      >
        Historial de Peleas
      </h3>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[700px]">
          <thead>
            <tr className="border-b border-border">
              {["Res.", "Oponente", "Método", "Rnd", "Evento", "Fecha", "Sig Str", "TD", "KD"].map((col) => (
                <th
                  key={col}
                  className="text-[10px] uppercase tracking-widest text-muted-foreground font-medium pb-2 text-left pr-3 last:pr-0"
                >
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sorted.map((fight) => (
              <tr
                key={fight.fight_index}
                onClick={() => onSelectFight(fight.fight_index)}
                className="border-b border-border/40 cursor-pointer hover:bg-card-hover transition-colors group"
              >
                <td className="py-2.5 pr-3">
                  <ResultBadge result={fight.result} />
                </td>
                <td className="py-2.5 pr-3">
                  <span className="text-sm text-foreground font-medium group-hover:text-accent transition-colors">
                    {fight.opponent}
                  </span>
                </td>
                <td className="py-2.5 pr-3">
                  <span className="text-xs text-muted">{fight.method || "—"}</span>
                </td>
                <td className="py-2.5 pr-3">
                  <span className="text-xs text-muted-foreground">{fight.round || "—"}</span>
                </td>
                <td className="py-2.5 pr-3 max-w-[120px]">
                  <span className="text-xs text-muted-foreground truncate block">{fight.event || "—"}</span>
                </td>
                <td className="py-2.5 pr-3">
                  <span className="text-xs text-muted-foreground whitespace-nowrap">
                    {fmtDate(fight.event_date)}
                  </span>
                </td>
                <td className="py-2.5 pr-3">
                  <span className="text-xs text-muted-foreground">
                    {fight.sig_str_landed}/{fight.sig_str_attempted}
                  </span>
                </td>
                <td className="py-2.5 pr-3">
                  <span className="text-xs text-muted-foreground">
                    {fight.td_landed}/{fight.td_attempted}
                  </span>
                </td>
                <td className="py-2.5">
                  <span
                    className={`text-xs font-medium ${
                      fight.kd_landed > 0 ? "text-accent" : "text-muted-foreground"
                    }`}
                  >
                    {fight.kd_landed}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </motion.div>
  );
}
