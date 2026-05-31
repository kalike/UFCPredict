import { useState } from "react";
import { motion } from "framer-motion";
import { GitCompareArrows, AlertTriangle, Trophy, Ban } from "lucide-react";
import type { RichFightPrediction } from "../../api/client";
import { PredictionBar } from "../compare/PredictionBar";
import { FighterAvatar } from "./FighterAvatar";
import { ConsensusBadge } from "./ConsensusBadge";
import { FightMethodBars } from "./FightMethodBars";
import { CommunityPicksBar } from "./CommunityPicksBar";
import { ModelChips } from "./ModelChips";
import { CompareModal } from "./CompareModal";
import { fmtOdds } from "./utils";

interface FightCardProps {
  fight: RichFightPrediction;
  canMark?: boolean;
  onMark?: (winner: string | null) => void;
}

export function FightCard({ fight, canMark = false, onMark }: FightCardProps) {
  const [compareOpen, setCompareOpen] = useState(false);
  const { fighter_1: f1, fighter_2: f2, real_winner, consensus } = fight;

  const noHistory = !fight.fighter_1_has_history || !fight.fighter_2_has_history;
  const noHistoryNames = [
    !fight.fighter_1_has_history ? f1 : null,
    !fight.fighter_2_has_history ? f2 : null,
  ].filter(Boolean).join(", ");

  function highlight(name: string): "winner" | "loser" | "neutral" {
    if (!real_winner) return "neutral";
    return real_winner === name ? "winner" : "loser";
  }

  function handleMark(name: string) {
    if (!canMark || !onMark) return;
    onMark(real_winner === name ? null : name);
  }

  const pickWinner = consensus?.consensus_winner;

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="rounded-lg border border-border bg-card p-4 space-y-3"
    >
      {/* Banners */}
      {real_winner && (
        <div className="flex items-center gap-2 rounded-md bg-success/10 border border-success/30 px-3 py-1.5 text-xs text-success">
          <Trophy size={13} /> Ganador real: <span className="font-semibold">{real_winner}</span>
        </div>
      )}
      {!real_winner && fight.outcome && (
        <div className="flex items-center gap-2 rounded-md bg-white/5 border border-border px-3 py-1.5 text-xs text-muted-foreground">
          <Ban size={13} /> Sin ganador · {fight.outcome === "nc" ? "No Contest" : "Empate"}
        </div>
      )}
      {noHistory && (
        <div className="flex items-center gap-2 rounded-md bg-warning/10 border border-warning/30 px-3 py-1.5 text-xs text-warning">
          <AlertTriangle size={13} /> Sin historial: {noHistoryNames}
        </div>
      )}

      {/* Pick banner */}
      {pickWinner && consensus && (
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <span className="text-sm">
            <span className="text-muted-foreground">Pick: </span>
            <span className="font-semibold text-foreground">{pickWinner}</span>
          </span>
          <ConsensusBadge consensus={consensus} />
        </div>
      )}

      {/* Avatars + VS */}
      <div className="flex items-center justify-between gap-3">
        <div className="flex flex-col items-center gap-1.5 flex-1 min-w-0">
          <FighterAvatar
            name={f1}
            highlight={highlight(f1)}
            markable={canMark}
            onMark={() => handleMark(f1)}
          />
          <span className="text-xs font-medium text-center truncate w-full">{f1}</span>
          <span className="text-[10px] text-muted-foreground tabular-nums">{fmtOdds(fight.odds_f1_american)}</span>
        </div>
        <span className="font-display text-xl text-muted-foreground/40 shrink-0">VS</span>
        <div className="flex flex-col items-center gap-1.5 flex-1 min-w-0">
          <FighterAvatar
            name={f2}
            highlight={highlight(f2)}
            markable={canMark}
            onMark={() => handleMark(f2)}
          />
          <span className="text-xs font-medium text-center truncate w-full">{f2}</span>
          <span className="text-[10px] text-muted-foreground tabular-nums">{fmtOdds(fight.odds_f2_american)}</span>
        </div>
      </div>

      {/* Ensemble probability */}
      <PredictionBar fighter1={f1} fighter2={f2} probF1={fight.prob_f1} size="md" />

      {/* Method bars */}
      <FightMethodBars f1={f1} f2={f2} m1={fight.fighter_1_methods} m2={fight.fighter_2_methods} />

      {/* Community picks */}
      {fight.community_picks && fight.community_picks.total_picks > 0 && (
        <CommunityPicksBar cp={fight.community_picks} f1={f1} f2={f2} />
      )}

      {/* Per-model chips */}
      <ModelChips models={fight.models} realWinner={real_winner} />

      {/* Actions */}
      <div className="flex items-center gap-2 pt-1">
        <button
          onClick={() => setCompareOpen(true)}
          className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-accent transition-colors"
        >
          <GitCompareArrows size={14} /> Comparar
        </button>
      </div>

      {compareOpen && <CompareModal f1={f1} f2={f2} onClose={() => setCompareOpen(false)} />}
    </motion.div>
  );
}
