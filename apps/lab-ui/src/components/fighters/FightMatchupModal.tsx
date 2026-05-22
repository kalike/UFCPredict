import * as Dialog from "@radix-ui/react-dialog";
import { Loader2, AlertCircle, X } from "lucide-react";
import { useFightMatchup } from "./useFighters";

interface FightMatchupModalProps {
  fighterName: string;
  fightIndex: number | null;
  onClose: () => void;
}

function fmtCtrl(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

interface MatchupStats {
  label: string;
  fKey: string;
  oKey: string;
  format?: (v: number, attempted?: number) => string;
  attemptedFKey?: string;
  attemptedOKey?: string;
  higherIsBetter?: boolean;
}

const STAT_ROWS: MatchupStats[] = [
  {
    label: "Sig Strikes",
    fKey: "sig_str_landed",
    oKey: "sig_str_landed",
    attemptedFKey: "sig_str_attempted",
    attemptedOKey: "sig_str_attempted",
    format: (v, att) => (att != null ? `${v}/${att}` : String(v)),
    higherIsBetter: true,
  },
  {
    label: "Knockdowns",
    fKey: "kd_landed",
    oKey: "kd_landed",
    format: (v) => String(v),
    higherIsBetter: true,
  },
  {
    label: "Takedowns",
    fKey: "td_landed",
    oKey: "td_landed",
    attemptedFKey: "td_attempted",
    attemptedOKey: "td_attempted",
    format: (v, att) => (att != null ? `${v}/${att}` : String(v)),
    higherIsBetter: true,
  },
  {
    label: "Sub Attempts",
    fKey: "sub_att",
    oKey: "sub_att",
    format: (v) => String(v),
    higherIsBetter: true,
  },
  {
    label: "Control",
    fKey: "ctrl_seconds",
    oKey: "ctrl_seconds",
    format: (v) => fmtCtrl(v),
    higherIsBetter: true,
  },
  {
    label: "Head",
    fKey: "head_landed",
    oKey: "head_landed",
    format: (v) => String(v),
    higherIsBetter: true,
  },
  {
    label: "Body",
    fKey: "body_landed",
    oKey: "body_landed",
    format: (v) => String(v),
    higherIsBetter: true,
  },
  {
    label: "Leg",
    fKey: "leg_landed",
    oKey: "leg_landed",
    format: (v) => String(v),
    higherIsBetter: true,
  },
];

function getStatValue(stats: Record<string, number>, key: string): number {
  return stats[key] ?? 0;
}

function isWin(result: string | undefined): boolean {
  return !!result && (result.toUpperCase().startsWith("W") || result === "win");
}

function MatchupContent({
  fighterName,
  fightIndex,
}: {
  fighterName: string;
  fightIndex: number;
}) {
  const { data, isLoading, isError } = useFightMatchup(fighterName, fightIndex);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-10">
        <Loader2 className="w-6 h-6 text-accent animate-spin" />
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="flex items-center gap-2 py-8 justify-center text-destructive text-sm">
        <AlertCircle size={16} />
        <span>Error cargando datos del combate</span>
      </div>
    );
  }

  return (
    <div>
      {/* Event / result header */}
      <div className="mb-5">
        <p className="text-muted-foreground text-xs mb-1">{data.event}</p>
        <p className="text-foreground text-sm">
          <span
            className={isWin(data.result) ? "text-success font-semibold" : "text-destructive font-semibold"}
          >
            {data.result}
          </span>
          {" "}by{" "}
          <span className="text-foreground font-medium">{data.method}</span>
          {", Round "}
          <span className="text-foreground font-medium">{data.round}</span>
        </p>
      </div>

      {/* Stats table */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border">
              <th className="text-left py-2 pr-2 text-accent text-xs font-semibold tracking-wide">
                {data.fighter}
              </th>
              <th className="text-center py-2 px-2 text-[10px] uppercase tracking-widest text-muted-foreground font-medium w-24">
                Stat
              </th>
              <th className="text-right py-2 pl-2 text-info text-xs font-semibold tracking-wide">
                {data.opponent}
              </th>
            </tr>
          </thead>
          <tbody>
            {STAT_ROWS.map((row) => {
              const fVal = getStatValue(data.fighter_stats, row.fKey);
              const oVal = getStatValue(data.opponent_stats, row.oKey);
              const fAtt = row.attemptedFKey
                ? getStatValue(data.fighter_stats, row.attemptedFKey)
                : undefined;
              const oAtt = row.attemptedOKey
                ? getStatValue(data.opponent_stats, row.attemptedOKey)
                : undefined;

              const fDisplay = row.format ? row.format(fVal, fAtt) : String(fVal);
              const oDisplay = row.format ? row.format(oVal, oAtt) : String(oVal);

              const fBetter = row.higherIsBetter ? fVal >= oVal : fVal <= oVal;
              const oBetter = row.higherIsBetter ? oVal >= fVal : oVal <= fVal;

              return (
                <tr key={row.label} className="border-b border-border/40">
                  <td className={`py-2.5 pr-2 text-left font-medium text-sm ${fBetter ? "text-accent" : "text-muted"}`}>
                    {fDisplay}
                  </td>
                  <td className="py-2.5 px-2 text-center">
                    <span className="text-[10px] uppercase tracking-widest text-muted-foreground">
                      {row.label}
                    </span>
                  </td>
                  <td className={`py-2.5 pl-2 text-right font-medium text-sm ${oBetter ? "text-info" : "text-muted"}`}>
                    {oDisplay}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function FightMatchupModal({
  fighterName,
  fightIndex,
  onClose,
}: FightMatchupModalProps) {
  return (
    <Dialog.Root open={fightIndex !== null} onOpenChange={(v) => !v && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-full max-w-lg -translate-x-1/2 -translate-y-1/2 bg-card border border-border rounded-xl p-6 shadow-2xl focus:outline-none">
          <div className="flex items-center justify-between mb-4">
            <Dialog.Title
              className="text-foreground text-lg font-semibold"
              style={{ fontFamily: "'Oswald', sans-serif" }}
            >
              Detalles del Combate
            </Dialog.Title>
            <Dialog.Close asChild>
              <button
                className="text-muted-foreground hover:text-foreground transition-colors"
                aria-label="Cerrar"
              >
                <X size={16} />
              </button>
            </Dialog.Close>
          </div>
          {fightIndex !== null && (
            <MatchupContent fighterName={fighterName} fightIndex={fightIndex} />
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
