import { useState } from "react";
import { ChevronDown, Check, X } from "lucide-react";
import type { ModelPrediction } from "../../api/client";
import { lastName, modelColor } from "./utils";

interface ModelChipsProps {
  models: Record<string, ModelPrediction>;
  realWinner?: string | null;
}

export function ModelChips({ models, realWinner }: ModelChipsProps) {
  const [open, setOpen] = useState(false);
  const entries = Object.entries(models);

  return (
    <div>
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-1.5 text-[11px] uppercase tracking-widest text-muted-foreground hover:text-foreground transition-colors"
      >
        <ChevronDown size={13} className={`transition-transform ${open ? "rotate-180" : ""}`} />
        Predicciones por modelo ({entries.length})
      </button>
      {open && (
        <div className="grid grid-cols-2 gap-1.5 mt-2">
          {entries.map(([short, mp]) => {
            const correct = realWinner
              ? mp.predicted_winner === realWinner
              : null;
            return (
              <div
                key={short}
                className="flex items-center gap-2 rounded-md bg-white/[0.02] border-l-2 pl-2 pr-2 py-1"
                style={{ borderLeftColor: modelColor(short) }}
              >
                <span className="text-[10px] font-mono text-muted-foreground w-10 shrink-0">{short}</span>
                <span className="text-[11px] text-foreground truncate flex-1">
                  {lastName(mp.predicted_winner)}
                </span>
                <span className="text-[10px] tabular-nums text-muted-foreground">
                  {(mp.confidence * 100).toFixed(0)}%
                </span>
                {correct === true && <Check size={12} className="text-success shrink-0" />}
                {correct === false && <X size={12} className="text-destructive shrink-0" />}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
