import { useEffect } from "react";
import { createPortal } from "react-dom";
import { X, Loader2 } from "lucide-react";
import { useCompare } from "../compare/useCompare";
import { CompareHeader } from "../compare/CompareHeader";
import { CompareRadar } from "../compare/CompareRadar";
import { CompareStatCards } from "../compare/CompareStatCards";
import { FeatureDeltaTable } from "../compare/FeatureDeltaTable";
import { FighterRecentFights } from "../compare/FighterRecentFights";

interface CompareModalProps {
  f1: string;
  f2: string;
  onClose: () => void;
}

export function CompareModal({ f1, f2, onClose }: CompareModalProps) {
  const { data, isLoading, isError } = useCompare(f1, f2);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  return createPortal(
    <div className="fixed inset-0 z-[100] flex items-start justify-center bg-black/70 backdrop-blur-sm overflow-y-auto p-4 sm:p-8">
      <div
        className="relative w-full max-w-5xl bg-background border border-border rounded-xl shadow-2xl my-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sticky top-0 z-10 flex items-center justify-between px-5 py-3 border-b border-border bg-background/95 backdrop-blur rounded-t-xl">
          <h3 className="font-display text-lg uppercase tracking-wide">
            {f1} <span className="text-muted-foreground">vs</span> {f2}
          </h3>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground transition-colors">
            <X size={20} />
          </button>
        </div>

        <div className="p-5 space-y-5">
          {isLoading && (
            <div className="flex items-center justify-center py-20 text-muted-foreground gap-2">
              <Loader2 className="animate-spin" size={18} /> Cargando comparación…
            </div>
          )}
          {isError && (
            <div className="bg-destructive/10 border border-destructive/30 rounded-lg p-6 text-center text-destructive">
              Error cargando la comparación
            </div>
          )}
          {data && (
            <>
              <CompareHeader data={data} />
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
                <CompareRadar
                  f1={data.fighter_1}
                  f2={data.fighter_2}
                  f1Name={data.fighter_1.name}
                  f2Name={data.fighter_2.name}
                />
                <CompareStatCards data={data} />
              </div>
              <FeatureDeltaTable
                deltas={data.feature_deltas}
                f1Name={data.fighter_1.name}
                f2Name={data.fighter_2.name}
              />
              <FighterRecentFights
                f1Name={data.fighter_1.name}
                f2Name={data.fighter_2.name}
                fights1={data.recent_fights_f1}
                fights2={data.recent_fights_f2}
              />
            </>
          )}
        </div>
      </div>
    </div>,
    document.body,
  );
}
