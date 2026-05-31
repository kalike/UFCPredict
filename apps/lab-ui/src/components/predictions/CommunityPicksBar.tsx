import type { CommunityPicks, CommunityMethod } from "../../api/client";

function FighterBar({ name, winPct, methods }: { name: string; winPct: number; methods: CommunityMethod }) {
  // win_pct + method pcts come from Tapology already in 0–100 scale.
  const wp = Math.max(0, Math.min(100, Math.round(winPct)));
  return (
    <div className="space-y-1">
      <div className="flex items-baseline justify-between gap-2">
        <span className="truncate text-xs text-foreground max-w-[75%]">{name}</span>
        <span className="text-[11px] text-amber-400 tabular-nums">{wp}%</span>
      </div>
      <div className="h-2.5 rounded-full bg-white/5 overflow-hidden">
        <div className="h-full flex" style={{ width: `${wp}%` }}>
          <div className="h-full bg-amber-700" style={{ width: `${methods.ko_tko_pct}%` }} title={`KO/TKO ${methods.ko_tko_pct.toFixed(0)}%`} />
          <div className="h-full bg-amber-500" style={{ width: `${methods.submission_pct}%` }} title={`SUB ${methods.submission_pct.toFixed(0)}%`} />
          <div className="h-full bg-amber-300" style={{ width: `${methods.decision_pct}%` }} title={`DEC ${methods.decision_pct.toFixed(0)}%`} />
        </div>
      </div>
    </div>
  );
}

export function CommunityPicksBar({ cp, f1, f2 }: { cp: CommunityPicks; f1: string; f2: string }) {
  return (
    <div className="rounded-md bg-white/[0.02] border border-border/60 p-3 space-y-2.5">
      <div className="flex items-center justify-between">
        <span className="text-[10px] uppercase tracking-widest text-muted-foreground">Comunidad (Tapology)</span>
        <span className="text-[10px] text-muted-foreground tabular-nums">{cp.total_picks} picks</span>
      </div>

      <FighterBar name={f1} winPct={cp.fighter_1_win_pct} methods={cp.fighter_1_methods} />
      <FighterBar name={f2} winPct={cp.fighter_2_win_pct} methods={cp.fighter_2_methods} />

      <div className="flex justify-end gap-2.5 text-[9px] text-muted-foreground pt-0.5">
        <span><span className="text-amber-700">■</span> KO/TKO</span>
        <span><span className="text-amber-500">■</span> SUB</span>
        <span><span className="text-amber-300">■</span> DEC</span>
      </div>
    </div>
  );
}
