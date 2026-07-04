import type { QualifiedPick } from "../../api/client";
import { Card } from "../ui";

// localStorage helpers — keys must stay identical to the legacy backend so existing
// state is reused: betting_exclusions_{sessionId}.
const STORAGE_PREFIX = "betting_exclusions_";

export function loadExclusions(sessionId: number): string[] {
  try {
    const raw = localStorage.getItem(STORAGE_PREFIX + sessionId);
    return raw ? (JSON.parse(raw) as string[]) : [];
  } catch {
    return [];
  }
}

export function saveExclusions(sessionId: number, excluded: string[]) {
  localStorage.setItem(STORAGE_PREFIX + sessionId, JSON.stringify(excluded));
}

export function pickKey(p: QualifiedPick): string {
  return `${p.fighter_1} vs ${p.fighter_2}`;
}

type Props = {
  picks: QualifiedPick[];
  excludedPicks: string[];
  onToggle: (key: string) => void;
};

export function PickSelector({ picks, excludedPicks, onToggle }: Props) {
  const excludedSet = new Set(excludedPicks);

  return (
    <Card>
      <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-widest mb-1">
        Picks cualificados
      </h3>
      <p className="text-xs text-muted-foreground mb-3">
        Desmarca los picks que no quieras incluir en las apuestas.
      </p>
      <div className="space-y-1">
        <div className="grid grid-cols-[auto_2fr_1fr_1fr_1fr_1fr_1fr] gap-3 px-3 py-1.5 text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">
          <span className="w-5" />
          <span>Pick</span>
          <span className="text-right">Prob</span>
          <span className="text-right">Odds</span>
          <span className="text-right">Edge</span>
          <span className="text-right">EV</span>
          <span className="text-right">Score</span>
        </div>
        {picks.map((p) => {
          const key = pickKey(p);
          const isExcluded = excludedSet.has(key);
          return (
            <label
              key={key}
              className={`grid grid-cols-[auto_2fr_1fr_1fr_1fr_1fr_1fr] gap-3 items-center px-3 py-2 rounded cursor-pointer transition-colors text-xs ${
                isExcluded ? "opacity-40 bg-white/[0.02]" : "bg-white/5 hover:bg-white/10"
              }`}
            >
              <input
                type="checkbox"
                checked={!isExcluded}
                onChange={() => onToggle(key)}
                className="w-4 h-4 rounded accent-[var(--color-accent)]"
              />
              <div>
                <span className="font-medium text-foreground">{p.pick}</span>
                <span className="text-muted-foreground ml-1.5">
                  ({p.fighter_1} vs {p.fighter_2})
                </span>
              </div>
              <span className="text-right tabular-nums text-foreground">
                {(p.model_prob * 100).toFixed(1)}%
              </span>
              <span className="text-right tabular-nums text-muted-foreground">
                {p.pick_odds_american > 0 ? "+" : ""}
                {p.pick_odds_american}
              </span>
              <span
                className={`text-right tabular-nums font-medium ${
                  p.edge >= 0 ? "text-emerald-400" : "text-red-400"
                }`}
              >
                {(p.edge * 100).toFixed(1)}%
              </span>
              <span
                className={`text-right tabular-nums font-semibold ${
                  p.ev_per_unit >= 0 ? "text-emerald-400" : "text-red-400"
                }`}
              >
                {p.ev_per_unit >= 0 ? "+" : ""}
                {p.ev_per_unit.toFixed(3)}
              </span>
              <span className="text-right tabular-nums text-foreground">
                {p.score.toFixed(3)}
              </span>
            </label>
          );
        })}
      </div>
    </Card>
  );
}
