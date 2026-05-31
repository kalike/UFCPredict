import type { MethodBreakdown } from "../../api/client";

const METHODS: { key: "ko" | "sub" | "dec"; label: string }[] = [
  { key: "ko", label: "KO/TKO" },
  { key: "sub", label: "SUB" },
  { key: "dec", label: "DEC" },
];

function pct(n: number, total: number): number {
  return total > 0 ? Math.round((n / total) * 100) : 0;
}

function FighterMethods({ name, m, align }: { name: string; m: MethodBreakdown; align: "left" | "right" }) {
  const winsBy = { ko: m.ko_wins, sub: m.sub_wins, dec: m.dec_wins };
  const lossBy = { ko: m.ko_losses, sub: m.sub_losses, dec: m.dec_losses };
  return (
    <div className="flex-1 min-w-0 space-y-1.5">
      <div className={`flex items-baseline gap-1.5 ${align === "right" ? "justify-end" : ""}`}>
        <span className="truncate text-xs font-medium text-foreground max-w-[70%]">{name}</span>
        <span className="text-[10px] text-muted-foreground tabular-nums">{m.wins}-{m.losses}</span>
      </div>
      {METHODS.map(({ key, label }) => {
        const w = pct(winsBy[key], m.wins);
        const l = pct(lossBy[key], m.losses);
        return (
          <div key={key} className="flex items-center gap-2 text-[10px]">
            <span className="w-12 shrink-0 text-muted-foreground uppercase tracking-wide">{label}</span>
            <div className="flex-1 flex items-center gap-1">
              <div className="flex-1 h-1.5 rounded-full bg-white/5 overflow-hidden">
                <div className="h-full bg-success" style={{ width: `${w}%` }} />
              </div>
              <div className="flex-1 h-1.5 rounded-full bg-white/5 overflow-hidden">
                <div className="h-full bg-destructive/70" style={{ width: `${l}%` }} />
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

interface FightMethodBarsProps {
  f1: string;
  f2: string;
  m1: MethodBreakdown;
  m2: MethodBreakdown;
}

export function FightMethodBars({ f1, f2, m1, m2 }: FightMethodBarsProps) {
  return (
    <div className="rounded-md bg-white/[0.02] border border-border/60 p-3">
      <div className="flex items-center justify-between mb-2">
        <span className="text-[10px] uppercase tracking-widest text-muted-foreground">Métodos (carrera)</span>
        <span className="text-[9px] text-muted-foreground">
          <span className="text-success">■</span> victorias · <span className="text-destructive/70">■</span> derrotas
        </span>
      </div>
      <div className="flex gap-4">
        <FighterMethods name={f1} m={m1} align="left" />
        <FighterMethods name={f2} m={m2} align="left" />
      </div>
    </div>
  );
}
