import { useState } from "react";
import { Trash2, Loader2, ArrowUpRight, DownloadCloud } from "lucide-react";
import type { SessionSummary } from "../../api/client";
import { Button, Input } from "../ui";
import { fmtDate } from "../../lib/formatters";
import { FightCard } from "./FightCard";
import {
  useSessions, useSession, useMarkResult, usePromoteSession,
  useImportOdds, useDeleteSession, useDeleteAllSessions,
} from "./usePredictions";

function accPill(s: SessionSummary): { text: string; cls: string } {
  if (s.n_results === 0) return { text: "Sin resultados", cls: "bg-white/5 text-muted-foreground" };
  const acc = s.accuracy ?? 0;
  const cls = acc >= 0.6 ? "bg-success/15 text-success" : acc < 0.5 ? "bg-destructive/15 text-destructive" : "bg-warning/15 text-warning";
  return { text: `${(acc * 100).toFixed(0)}% · ${s.n_correct}/${s.n_results}`, cls };
}

function SessionDetailPanel({ id }: { id: number }) {
  const { data, isLoading } = useSession(id);
  const mark = useMarkResult(id);
  const promote = usePromoteSession(id);
  const importOdds = useImportOdds(id);
  const [evDate, setEvDate] = useState("");
  const [evLoc, setEvLoc] = useState("");
  const [tapUrl, setTapUrl] = useState("");

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
            {data.promoted && <span className="px-2 py-0.5 rounded text-[10px] uppercase tracking-widest bg-gold/15 text-gold">Promovida</span>}
          </h3>
          <p className="text-xs text-muted-foreground">
            {fmtDate(data.created_at)} · {data.n_fights} peleas
          </p>
        </div>
        {acc != null && (
          <span className="px-2.5 py-1 rounded-md text-sm font-semibold bg-success/15 text-success">
            {(acc * 100).toFixed(0)}% · {nCorrect}/{nResults}
          </span>
        )}
      </div>

      {/* Promote */}
      {!data.promoted && (
        <div className="rounded-lg border border-border bg-card p-4 space-y-2">
          <p className="text-[11px] uppercase tracking-widest text-muted-foreground">Promover a histórico</p>
          <div className="grid grid-cols-2 gap-2">
            <Input type="date" value={evDate} onChange={(e) => setEvDate(e.target.value)} />
            <Input placeholder="Lugar (opcional)" value={evLoc} onChange={(e) => setEvLoc(e.target.value)} />
          </div>
          <Button
            variant="secondary"
            onClick={() => promote.mutate({ event_date: evDate || null, event_location: evLoc || null })}
            disabled={promote.isPending}
          >
            {promote.isPending ? <Loader2 className="animate-spin inline" size={14} /> : <ArrowUpRight className="inline" size={14} />}
            <span className="ml-1.5">Promover a histórico</span>
          </Button>
        </div>
      )}

      {/* Import odds */}
      {data.promoted && (
        <div className="rounded-lg border border-border bg-card p-4 space-y-2">
          <p className="text-[11px] uppercase tracking-widest text-muted-foreground">Importar odds desde Tapology</p>
          <div className="flex gap-2">
            <Input placeholder="URL del evento Tapology" value={tapUrl} onChange={(e) => setTapUrl(e.target.value)} />
            <Button variant="secondary" onClick={() => importOdds.mutate(tapUrl)} disabled={!tapUrl || importOdds.isPending}>
              {importOdds.isPending ? <Loader2 className="animate-spin inline" size={14} /> : <DownloadCloud className="inline" size={14} />}
              <span className="ml-1.5">Importar</span>
            </Button>
          </div>
          {importOdds.data && (
            <p className="text-xs text-muted-foreground">
              {importOdds.data.ok
                ? `Actualizadas ${importOdds.data.updated} peleas${importOdds.data.not_matched.length ? ` · ${importOdds.data.not_matched.length} sin match` : ""}`
                : `Error: ${importOdds.data.error}`}
            </p>
          )}
        </div>
      )}

      <p className="text-[11px] text-muted-foreground">Haz clic en el avatar de un luchador para marcarlo como ganador.</p>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        {data.fights.map((f, i) => (
          <FightCard
            key={f.fight_id ?? i}
            fight={f}
            canMark
            onMark={(winner) => mark.mutate({ index: i, winner })}
          />
        ))}
      </div>
    </div>
  );
}

export function SessionsTab() {
  const { data: sessions, isLoading } = useSessions();
  const [selected, setSelected] = useState<number | null>(null);
  const del = useDeleteSession();
  const delAll = useDeleteAllSessions();

  return (
    <div className="grid grid-cols-1 lg:grid-cols-[20rem_1fr] gap-4">
      {/* List */}
      <div className="rounded-lg border border-border bg-card overflow-hidden flex flex-col">
        <div className="px-4 py-3 border-b border-border flex items-center justify-between">
          <span className="text-sm font-semibold">Sesiones</span>
          {(sessions?.length ?? 0) > 0 && (
            <button
              onClick={() => { if (confirm("¿Eliminar todas las sesiones?")) delAll.mutate(); }}
              className="text-[11px] text-muted-foreground hover:text-destructive transition-colors"
            >
              Eliminar todas
            </button>
          )}
        </div>
        <div className="flex-1 overflow-y-auto max-h-[70vh]">
          {isLoading ? (
            <div className="p-4 text-muted-foreground text-sm flex items-center gap-2"><Loader2 className="animate-spin" size={15} /> Cargando…</div>
          ) : (sessions?.length ?? 0) === 0 ? (
            <div className="p-6 text-center text-muted-foreground text-sm">No hay sesiones guardadas</div>
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
                    <Trash2
                      size={13}
                      className="opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-destructive transition-all shrink-0"
                      onClick={(e) => { e.stopPropagation(); del.mutate(s.id); if (selected === s.id) setSelected(null); }}
                    />
                  </div>
                  <div className="flex items-center justify-between gap-2 mt-1">
                    <span className="text-[10px] text-muted-foreground">{fmtDate(s.created_at)} · {s.n_fights}p</span>
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
          <SessionDetailPanel id={selected} />
        ) : (
          <div className="flex items-center justify-center h-full min-h-[16rem] text-muted-foreground text-sm">
            Selecciona una sesión para ver el detalle
          </div>
        )}
      </div>
    </div>
  );
}
