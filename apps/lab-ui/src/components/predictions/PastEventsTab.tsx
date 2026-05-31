import { useState } from "react";
import { Loader2 } from "lucide-react";
import { usePastEvents, usePastEventPredictions } from "./usePredictions";
import { FightCard } from "./FightCard";

function accColor(acc: number): string {
  if (acc >= 0.6) return "text-success";
  if (acc < 0.5) return "text-destructive";
  return "text-warning";
}

export function PastEventsTab() {
  const [selected, setSelected] = useState<string | null>(null);
  const events = usePastEvents();
  const preds = usePastEventPredictions(selected);

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-border bg-card p-4">
        <p className="text-[11px] uppercase tracking-widest text-muted-foreground mb-2">Evento histórico</p>
        {events.isLoading ? (
          <div className="flex items-center gap-2 text-muted-foreground text-sm"><Loader2 className="animate-spin" size={15} /> Cargando…</div>
        ) : events.isError ? (
          <p className="text-destructive text-sm">Error al cargar eventos</p>
        ) : (
          <select
            value={selected ?? ""}
            onChange={(e) => setSelected(e.target.value || null)}
            className="w-full bg-[var(--color-background)] border border-border rounded-md px-3 py-2 text-sm focus:border-accent focus:outline-none"
          >
            <option value="">Selecciona un evento…</option>
            {(events.data ?? []).map((e) => (
              <option key={e.name} value={e.name}>
                {e.name} ({e.n_fights} peleas){e.date ? ` — ${e.date.slice(0, 10)}` : ""}
              </option>
            ))}
          </select>
        )}
      </div>

      {selected && preds.isLoading && (
        <div className="flex items-center gap-2 text-muted-foreground text-sm"><Loader2 className="animate-spin" size={15} /> Calculando predicciones…</div>
      )}
      {selected && preds.isError && (
        <p className="text-destructive text-sm">Error al calcular predicciones</p>
      )}

      {preds.data && (
        <>
          {/* Accuracy summary */}
          <div className="rounded-lg border border-border bg-card p-4">
            <div className="flex items-center justify-between mb-3">
              <p className="text-[11px] uppercase tracking-widest text-muted-foreground">
                Accuracy por modelo
              </p>
              <span className="text-xs text-muted-foreground">{preds.data.n_fights_valid} peleas con resultado</span>
            </div>
            <div className="grid grid-cols-3 sm:grid-cols-4 lg:grid-cols-6 gap-2">
              {Object.entries(preds.data.accuracy).map(([short, a]) => (
                <div key={short} className="rounded-md bg-white/[0.02] border border-border/60 px-2 py-1.5 text-center" title={a.full_name}>
                  <div className="text-[10px] font-mono text-muted-foreground truncate">{short}</div>
                  <div className={`display-num text-base ${accColor(a.accuracy)}`}>{(a.accuracy * 100).toFixed(0)}%</div>
                  <div className="text-[9px] text-muted-foreground">{a.correct}/{a.total}</div>
                </div>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
            {preds.data.fights.map((f, i) => (
              <FightCard key={f.fight_id ?? i} fight={f} />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
