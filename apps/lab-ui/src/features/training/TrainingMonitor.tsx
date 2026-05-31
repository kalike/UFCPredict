import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, type TrainResult } from "../../api/client";
import { Card, Badge } from "../../components/ui";

function ProgressBar({ pct, tone = "accent" }: { pct: number; tone?: "accent" | "gold" }) {
  const color = tone === "gold" ? "var(--color-gold)" : "var(--color-accent)";
  return (
    <div className="h-2 rounded-full bg-[var(--color-border)] overflow-hidden">
      <div
        className="h-full rounded-full transition-all duration-500"
        style={{ width: `${Math.max(0, Math.min(100, pct))}%`, backgroundColor: color }}
      />
    </div>
  );
}

function Pct({ v, gold }: { v: number | null; gold?: boolean }) {
  if (v == null) return <span className="text-[var(--color-muted)]">—</span>;
  return <span className={gold && v > 0.65 ? "text-[var(--color-gold)]" : ""}>{(v * 100).toFixed(1)}%</span>;
}

function FeatureImportance({ items }: { items: TrainResult["feature_importance"] }) {
  if (!items?.length) return null;
  const max = items[0].importance || 1;
  return (
    <div className="space-y-1">
      <p className="text-[10px] uppercase tracking-widest text-[var(--color-muted)]">Feature importance</p>
      {items.slice(0, 15).map((f) => (
        <div key={f.feature} className="flex items-center gap-2">
          <span className="w-40 truncate text-right text-[10px] font-mono text-[var(--color-muted)]">{f.feature}</span>
          <div className="flex-1 h-2 rounded bg-[var(--color-border)]/40 overflow-hidden">
            <div className="h-full bg-[var(--color-accent)] rounded" style={{ width: `${(f.importance / max) * 100}%` }} />
          </div>
          <span className="w-12 text-[10px] font-mono text-[var(--color-muted)]">{f.importance.toFixed(3)}</span>
        </div>
      ))}
    </div>
  );
}

function RealworldBreakdown({ events }: { events: TrainResult["realworld_events"] }) {
  const [open, setOpen] = useState<string | null>(null);
  if (!events?.length) return null;
  return (
    <div className="space-y-1">
      <p className="text-[10px] uppercase tracking-widest text-[var(--color-muted)]">Realworld por evento</p>
      {events.map((ev) => {
        const acc = ev.total ? ev.correct / ev.total : 0;
        const isOpen = open === ev.event;
        return (
          <div key={ev.event} className="rounded border border-[var(--color-border)]/40">
            <button
              onClick={() => setOpen(isOpen ? null : ev.event)}
              className="w-full flex items-center justify-between px-2 py-1 text-left hover:bg-white/5"
            >
              <span className="text-[11px] truncate">{isOpen ? "▾" : "▸"} {ev.event}</span>
              <span className={`text-[11px] font-mono ${acc > 0.65 ? "text-[var(--color-gold)]" : acc < 0.5 ? "text-red-400" : ""}`}>
                {ev.correct}/{ev.total}
              </span>
            </button>
            {isOpen && (
              <div className="px-2 pb-1.5 space-y-0.5">
                {ev.fights.map((f, i) => (
                  <div key={i} className="flex items-center gap-1.5 text-[10px]">
                    <span className={f.correct ? "text-green-400" : "text-red-400"}>{f.correct ? "✓" : "✗"}</span>
                    <span className="text-[var(--color-muted)] truncate flex-1">{f.fighter_1} vs {f.fighter_2}</span>
                    <span className="font-mono">{f.predicted_winner}</span>
                    {!f.correct && <span className="text-red-400 font-mono">→ {f.real_winner}</span>}
                  </div>
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function ResultRow({ r }: { r: TrainResult }) {
  const [open, setOpen] = useState(false);
  const hasDetail = !r.error;
  return (
    <>
      <tr className="border-b border-[var(--color-border)]/40">
        <td className="py-1.5 px-2 font-mono">
          {r.model_short}
          {r.version_idx != null && <span className="text-[var(--color-muted)]"> v{r.version_idx}</span>}
        </td>
        <td className="py-1.5 px-2 font-mono text-right"><Pct v={r.accuracy} gold /></td>
        <td className="py-1.5 px-2 font-mono text-right">
          <Pct v={r.realworld_accuracy} gold />
          {r.realworld_total > 0 && (
            <span className="text-[9px] text-[var(--color-muted)] ml-1">{r.realworld_correct}/{r.realworld_total}</span>
          )}
        </td>
        <td className="py-1.5 px-2 text-right">
          {r.error ? <Badge tone="muted">error</Badge> : (
            <button onClick={() => setOpen((o) => !o)} className="text-[var(--color-accent)] text-xs hover:underline">
              {open ? "−" : "detalle"}
            </button>
          )}
        </td>
      </tr>
      {r.error && (
        <tr><td colSpan={4} className="px-2 pb-1.5 text-[10px] text-red-400">{r.error}</td></tr>
      )}
      {open && hasDetail && (
        <tr>
          <td colSpan={4} className="px-2 pb-3 pt-1">
            <div className="space-y-3">
              <div className="flex flex-wrap gap-x-4 gap-y-1 text-[10px] text-[var(--color-muted)] font-mono">
                <span>{r.job_label}</span>
                <span>train={r.n_train}</span>
                <span>test-val={r.n_test}</span>
                <span>logloss={r.log_loss?.toFixed(4) ?? "—"}</span>
                <span>auc={r.auc?.toFixed(3) ?? "—"}</span>
                <span>overfit={r.overfit_gap?.toFixed(3) ?? "—"}</span>
              </div>
              <RealworldBreakdown events={r.realworld_events} />
              <FeatureImportance items={r.feature_importance} />
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

export function TrainingMonitor() {
  const status = useQuery({
    queryKey: ["train-status"],
    queryFn: api.trainStatus,
    refetchInterval: (q) => (q.state.data?.is_running ? 1200 : false),
  });
  const s = status.data;
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [s?.logs]);

  const running = s?.is_running ?? false;
  const globalPct = s && s.n_jobs > 0 ? (s.job_index / s.n_jobs) * 100 : 0;

  return (
    <Card>
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-display text-sm uppercase tracking-widest text-[var(--color-muted)]">Monitor</h3>
        <Badge tone={running ? "accent" : "muted"}>{running ? "running" : "idle"}</Badge>
      </div>

      {!s ? (
        <p className="text-sm text-[var(--color-muted)]">…</p>
      ) : (
        <div className="space-y-4">
          {s.n_jobs > 1 && (
            <div>
              <div className="flex justify-between text-[10px] uppercase tracking-widest text-[var(--color-muted)] mb-1">
                <span>Batch</span>
                <span>Job {Math.min(s.job_index + (running ? 1 : 0), s.n_jobs)} / {s.n_jobs}</span>
              </div>
              <ProgressBar pct={running ? globalPct : 100} tone="gold" />
            </div>
          )}

          <div>
            <div className="flex justify-between text-xs mb-1">
              <span className="font-mono text-[var(--color-foreground)]">{s.model_short ?? "—"}</span>
              <span className="font-mono text-[var(--color-muted)]">{s.pct.toFixed(0)}%</span>
            </div>
            <ProgressBar pct={s.pct} />
            <p className="mt-1 text-[10px] text-[var(--color-muted)] font-mono">{s.step ?? "—"}</p>
            {s.job_label && <p className="text-[10px] text-[var(--color-muted)]/70">{s.job_label}</p>}
          </div>

          {s.logs && s.logs.length > 0 && (
            <div
              ref={logRef}
              className="max-h-40 overflow-auto rounded-md p-2 font-mono text-[11px] leading-relaxed"
              style={{ backgroundColor: "#050510", color: "rgba(34,197,94,0.85)" }}
            >
              {s.logs.map((line, i) => (
                <div key={i}>&gt; {line}</div>
              ))}
              {running && <span className="animate-pulse">▋</span>}
            </div>
          )}

          {s.error && (
            <div className="rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-400">
              {s.error}
            </div>
          )}

          {s.results && s.results.length > 0 && (
            <div>
              <h4 className="text-[10px] uppercase tracking-widest text-[var(--color-muted)] mb-1.5">Resultados</h4>
              <table className="w-full text-sm">
                <thead className="text-[10px] uppercase tracking-widest text-[var(--color-muted)] border-b border-[var(--color-border)]">
                  <tr>
                    <th className="text-left py-1.5 px-2">Modelo</th>
                    <th className="text-right py-1.5 px-2">Test-Val</th>
                    <th className="text-right py-1.5 px-2">Real World</th>
                    <th className="text-right py-1.5 px-2"></th>
                  </tr>
                </thead>
                <tbody>
                  {s.results.map((r, i) => <ResultRow key={`${r.model_short}-${i}`} r={r} />)}
                </tbody>
              </table>
            </div>
          )}

          {!running && (!s.results || s.results.length === 0) && (
            <p className="text-sm text-[var(--color-muted)]">Sin entrenamiento activo.</p>
          )}
        </div>
      )}
    </Card>
  );
}
