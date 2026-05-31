import { motion } from "framer-motion";
import type { RecentFight } from "../../api/client";
import { fmtDate } from "../../lib/formatters";

interface FighterRecentFightsProps {
  f1Name: string;
  f2Name: string;
  fights1: RecentFight[];
  fights2: RecentFight[];
}

function resultBadgeClass(result: string): string {
  const r = result.toUpperCase();
  if (r === "W" || r === "WIN") return "bg-success/10 text-success border-success/30";
  if (r === "L" || r === "LOSS") return "bg-destructive/10 text-destructive border-destructive/30";
  return "bg-border text-muted-foreground border-border";
}

function resultLabel(result: string): string {
  const r = result.toUpperCase();
  if (r === "W" || r === "WIN") return "W";
  if (r === "L" || r === "LOSS") return "L";
  return result.charAt(0).toUpperCase();
}

function FightList({ fights, side }: { fights: RecentFight[]; side: "left" | "right" }) {
  const recent = fights.slice(0, 5);

  if (recent.length === 0) {
    return (
      <p className="text-muted-foreground text-sm italic py-3">
        Sin historial disponible
      </p>
    );
  }

  return (
    <ul className="space-y-2">
      {recent.map((fight, i) => (
        <motion.li
          key={i}
          initial={{ opacity: 0, x: side === "left" ? -10 : 10 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.3, delay: i * 0.07 }}
          className="flex items-start gap-2 py-1.5 border-b border-border/20 last:border-0"
        >
          <span
            className={`flex-shrink-0 inline-flex items-center justify-center w-6 h-6 rounded text-[10px] font-bold border ${resultBadgeClass(fight.result)}`}
          >
            {resultLabel(fight.result)}
          </span>
          <div className="flex-1 min-w-0">
            <p className="text-foreground text-xs font-medium truncate leading-snug">
              {fight.opponent}
            </p>
            <p className="text-muted-foreground text-[10px] leading-snug truncate">
              {fight.method}
              {fight.round && fight.round !== "—" ? ` · R${fight.round}` : ""}
            </p>
            {fight.event && (
              <p className="text-muted text-[9px] leading-snug truncate" title={fight.event}>
                {fight.event}
              </p>
            )}
            {fight.event_date && (
              <p className="text-muted text-[9px] leading-snug">
                {fmtDate(fight.event_date)}
              </p>
            )}
          </div>
        </motion.li>
      ))}
    </ul>
  );
}

export function FighterRecentFights({ f1Name, f2Name, fights1, fights2 }: FighterRecentFightsProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay: 0.2 }}
      className="bg-card border border-border rounded-xl p-5 space-y-4"
    >
      <h3 className="text-muted-foreground text-xs uppercase tracking-widest font-semibold">
        Últimas peleas
      </h3>
      <div className="grid grid-cols-2 gap-4">
        {/* Fighter 1 */}
        <div className="space-y-2">
          <p className="text-[10px] uppercase tracking-widest font-semibold text-accent border-b border-accent/20 pb-1">
            {f1Name}
          </p>
          <FightList fights={fights1} side="left" />
        </div>

        {/* Fighter 2 */}
        <div className="space-y-2">
          <p className="text-[10px] uppercase tracking-widest font-semibold text-info border-b border-info/20 pb-1">
            {f2Name}
          </p>
          <FightList fights={fights2} side="right" />
        </div>
      </div>
    </motion.div>
  );
}
