import type { Consensus } from "../../api/client";

export function ConsensusBadge({ consensus }: { consensus: Consensus }) {
  const { consensus_pct, total_models } = consensus;
  const votes = Math.max(consensus.fighter_1_votes, consensus.fighter_2_votes);

  let label: string;
  let tone: string;
  if (consensus_pct >= 100) {
    label = "UNÁNIME";
    tone = "bg-success/15 text-success border-success/30";
  } else if (consensus_pct >= 66) {
    label = "MAYORÍA";
    tone = "bg-accent/15 text-accent border-accent/30";
  } else {
    label = "DIVIDIDO";
    tone = "bg-warning/15 text-warning border-warning/30";
  }

  return (
    <span
      className={`px-2 py-0.5 rounded text-[10px] font-semibold uppercase tracking-widest border ${tone}`}
    >
      {label} · {consensus_pct.toFixed(0)}% ({votes}/{total_models})
    </span>
  );
}
