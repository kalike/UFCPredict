import { useState } from "react";
import { Loader2 } from "lucide-react";
import type { SessionSummary } from "../../api/client";
import { fmtDate } from "../../lib/formatters";
import { FightCard } from "./FightCard";
import { useRealworldSessions, useSession } from "./usePredictions";

function accPill(s: SessionSummary): { text: string; cls: string } {
  if (s.n_results === 0) return { text: "Sin resultados", cls: "bg-white/5 text-muted-foreground" };
  const acc = s.accuracy ?? 0;
  const cls = acc >= 0.6 ? "bg-success/15 text-success" : acc < 0.5 ? "bg-destructive/15 text-destructive" : "bg-warning/15 text-warning";
  return { text: `${(acc * 100).toFixed(0)}% · ${s.n_correct}/${s.n_results}`, cls };
}

function RealworldDetailPanel({ id }: { id: number }) {
  const { data, isLoading } = useSession(id);

  if (isLoading || !data) {
    return <div className="flex items-center gap-2 text-muted-foreground text-sm p-6"><Loader2 className="animate-spin" size={15} /> Cargando…</div>;
  }

  const nResults = data.fights.filter((f) => f.real_winner).length;
  const nCorrect = data.fights.filter((f) => f.real_winner && f.consensus?.consensus_winner === f.real_winner).length;
  const acc = nResults > 0 ? nCorrect / nResults : null;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h3 className="font-display text-lg uppercase tracking-wide flex items-center gap-2">
            {data.event}
            <span className="px-2 py-0.5 rounded text-[10px] uppercase tracking-widest bg-accent/15 text-accent">RealWorld</span>
          </h3>
          <p className="text-xs text-muted-foreground">
            {data.event_date ? fmtDate(data.event_date) : fmtDate(data.created_at)} · {data.n_fights} peleas
          </p>
        </div>
        {acc != null && (
          <span className="px-2.5 py-1 rounded-md text-sm font-semibold bg-success/15 text-success">
            {(acc * 100).toFixed(0)}% · {nCorrect}/{nResults}
          </span>
        )}
      </div>

      <p className="text-[11px] text-muted-foreground">
        Evaluación out-of-sample generada por el recálculo. Solo lectura — los resultados reales provienen del histórico.
      </p>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        {data.fights.map((f, i) => (
          <FightCard key={f.fight_id ?? i} fight={f} />
        ))}
      </div>
    </div>
  );
}

export function RealworldSessionsTab() {
  const { data: sessions, isLoading } = useRealworldSessions();
  const [selected, setSelected] = useState<number | null>(null);

  return (
    <div className="grid grid-cols-1 lg:grid-cols-[20rem_1fr] gap-4">
      {/* List */}
      <div className="rounded-lg border border-border bg-card overflow-hidden flex flex-col">
        <div className="px-4 py-3 border-b border-border flex items-center justify-between">
          <span className="text-sm font-semibold">Eventos RealWorld</span>
          {(sessions?.length ?? 0) > 0 && (
            <span className="text-[11px] text-muted-foreground">{sessions!.length}</span>
          )}
        </div>
        <div className="flex-1 overflow-y-auto max-h-[70vh]">
          {isLoading ? (
            <div className="p-4 text-muted-foreground text-sm flex items-center gap-2"><Loader2 className="animate-spin" size={15} /> Cargando…</div>
          ) : (sessions?.length ?? 0) === 0 ? (
            <div className="p-6 text-center text-muted-foreground text-sm">
              No hay sesiones RealWorld. Lanza un recálculo desde la página de Recálculo.
            </div>
          ) : (
            sessions!.map((s) => {
              const pill = accPill(s);
              return (
                <button
                  key={s.id}
                  onClick={() => setSelected(s.id)}
                  className={`group w-full text-left px-4 py-3 border-b border-border/40 transition-colors ${selected === s.id ? "bg-accent/10" : "hover:bg-card-hover"}`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm font-medium truncate">{s.event}</span>
                  </div>
                  <div className="flex items-center justify-between gap-2 mt-1">
                    <span className="text-[10px] text-muted-foreground">{s.event_date ? fmtDate(s.event_date) : fmtDate(s.created_at)} · {s.n_fights}p</span>
                    <span className={`px-1.5 py-0.5 rounded text-[9px] uppercase tracking-wide ${pill.cls}`}>{pill.text}</span>
                  </div>
                </button>
              );
            })
          )}
        </div>
      </div>

      {/* Detail */}
      <div>
        {selected != null ? (
          <RealworldDetailPanel id={selected} />
        ) : (
          <div className="flex items-center justify-center h-full min-h-[16rem] text-muted-foreground text-sm">
            Selecciona un evento para ver el detalle
          </div>
        )}
      </div>
    </div>
  );
}
