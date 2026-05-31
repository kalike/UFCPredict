import { Save, Check, Loader2, AlertTriangle } from "lucide-react";
import type { PredictResponse, SessionFightIn } from "../../api/client";
import { Button } from "../ui";
import { FightCard } from "./FightCard";
import { useSaveSession } from "./usePredictions";

export function PredictionResults({ data }: { data: PredictResponse }) {
  const save = useSaveSession();

  function handleSave() {
    const fights: SessionFightIn[] = data.fights.map((f) => ({
      fighter_1: f.fighter_1,
      fighter_2: f.fighter_2,
      odds_f1_american: f.odds_f1_american,
      odds_f2_american: f.odds_f2_american,
      models: f.models,
      consensus_winner: f.consensus?.consensus_winner ?? null,
      consensus_pct: f.consensus?.consensus_pct ?? null,
      avg_prob_f1: f.prob_f1,
      community_picks: f.community_picks,
    }));
    save.mutate({ event: data.event, fights });
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h3 className="font-display text-lg uppercase tracking-wide">{data.event}</h3>
          <p className="text-xs text-muted-foreground">
            {data.fights.length} peleas · {data.n_models} modelos
          </p>
        </div>
        <Button onClick={handleSave} disabled={save.isPending || save.isSuccess}>
          {save.isPending ? <Loader2 className="animate-spin inline" size={15} />
            : save.isSuccess ? <Check className="inline" size={15} />
            : <Save className="inline" size={15} />}
          <span className="ml-1.5">{save.isSuccess ? "Sesión guardada" : "Guardar sesión"}</span>
        </Button>
      </div>

      {data.skipped.length > 0 && (
        <div className="flex items-start gap-2 rounded-md bg-warning/10 border border-warning/30 px-3 py-2 text-xs text-warning">
          <AlertTriangle size={14} className="mt-0.5 shrink-0" />
          <span>Peleas omitidas (sin historial): {data.skipped.join("; ")}</span>
        </div>
      )}
      {save.isError && (
        <div className="rounded-md bg-destructive/10 border border-destructive/30 px-3 py-2 text-xs text-destructive">
          {(save.error as Error).message}
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        {data.fights.map((f, i) => (
          <FightCard key={`${f.fighter_1}-${f.fighter_2}-${i}`} fight={f} />
        ))}
      </div>
    </div>
  );
}
