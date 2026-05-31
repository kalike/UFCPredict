import { useState } from "react";
import { ChevronDown, ChevronRight, CheckCircle2, XCircle } from "lucide-react";
import type { ModelMetrics, RealworldEvent, RealworldValue } from "../../api/client";
import { ConfusionMatrix } from "./ConfusionMatrix";

const OSWALD = { fontFamily: "'Oswald', sans-serif" } as const;

function fmtPct(v: number | null | undefined): string {
  return v != null ? `${(v * 100).toFixed(1)}%` : "—";
}

function MetricRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between py-1.5 border-b border-border/30 last:border-0">
      <span className="text-[11px] text-muted-foreground uppercase tracking-wider">{label}</span>
      <span className="text-sm text-foreground font-bold" style={OSWALD}>{value}</span>
    </div>
  );
}

export function VersionDetailPanel({
  metrics, params, origin,
}: { metrics: ModelMetrics; params?: Record<string, unknown> | null; origin?: string }) {
  const [rwOpen, setRwOpen] = useState(false);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const toggle = (ev: string) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      next.has(ev) ? next.delete(ev) : next.add(ev);
      return next;
    });

  const fi = metrics.feature_importance ?? null;
  // Newest first; events without a date sink to the end.
  const rwEvents = [...(metrics.realworld_events ?? [])].sort(
    (a, b) => (b.date ?? "").localeCompare(a.date ?? ""),
  );
  const gap = metrics.overfit_gap ?? 0;

  return (
    <div className="space-y-4">
      {/* Metrics + Confusion Matrix + Feature Importance */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Metrics */}
        <div>
          <h4 className="text-[11px] text-muted-foreground uppercase tracking-wider mb-2">
            Métricas de Evaluación
          </h4>
          <MetricRow label="Accuracy" value={fmtPct(metrics.accuracy)} />
          <MetricRow label="Precision" value={fmtPct(metrics.precision)} />
          <MetricRow label="Recall" value={fmtPct(metrics.recall)} />
          <MetricRow label="F1 Score" value={fmtPct(metrics.f1)} />
          <MetricRow label="AUC" value={fmtPct(metrics.auc)} />
          <MetricRow label="Log Loss" value={metrics.log_loss != null ? metrics.log_loss.toFixed(4) : "—"} />
          <MetricRow label="Train Accuracy" value={fmtPct(metrics.train_accuracy)} />
          <div className="flex items-center justify-between py-1.5">
            <span className="text-[11px] text-muted-foreground uppercase tracking-wider">Overfit Gap</span>
            <span
              className={["text-sm font-bold", gap > 0.05 ? "text-warning" : "text-muted-foreground"].join(" ")}
              style={OSWALD}
            >
              {gap >= 0 ? "+" : ""}{(gap * 100).toFixed(1)}%
            </span>
          </div>
          <div className="mt-1 text-[11px] text-muted-foreground">
            n_train: {metrics.n_train ?? "—"} &middot; n_test: {metrics.n_test ?? "—"}
            {metrics.n_features != null && <> &middot; features: {metrics.n_features}</>}
          </div>
        </div>

        {/* Confusion Matrix */}
        <div>
          <h4 className="text-[11px] text-muted-foreground uppercase tracking-wider mb-2">
            Matriz de Confusión
          </h4>
          {metrics.confusion_matrix ? (
            <ConfusionMatrix matrix={metrics.confusion_matrix} />
          ) : (
            <p className="text-[11px] text-muted-foreground">No disponible (re-entrena para generarla)</p>
          )}
        </div>

        {/* Feature Importance Top 30 */}
        <div>
          <h4 className="text-[11px] text-muted-foreground uppercase tracking-wider mb-2">
            Top 30 Features
          </h4>
          {fi && fi.length > 0 ? (
            <div className="space-y-1">
              {[...fi].sort((a, b) => b.importance - a.importance).slice(0, 30).map((f, i, arr) => {
                const maxImp = arr[0].importance;
                const pct = maxImp > 0 ? (f.importance / maxImp) * 100 : 0;
                return (
                  <div key={f.feature} className="flex items-center gap-2">
                    <span className="text-[10px] text-muted-foreground w-4 text-right shrink-0">{i + 1}</span>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between">
                        <span className="text-[10px] text-foreground truncate" title={f.feature}>{f.feature}</span>
                        <span className="text-[10px] text-muted-foreground ml-1 shrink-0" style={OSWALD}>
                          {f.importance.toFixed(3)}
                        </span>
                      </div>
                      <div className="h-1 bg-border/40 rounded-full mt-0.5">
                        <div className="h-full bg-accent/60 rounded-full" style={{ width: `${pct}%` }} />
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <p className="text-[11px] text-muted-foreground">
              No disponible{origin && origin.includes("pytorch") ? " (Deep no expone importancias)" : ""}
            </p>
          )}
        </div>
      </div>

      {/* Hyperparameters */}
      {params && Object.keys(params).length > 0 && (
        <div>
          <h4 className="text-[11px] text-muted-foreground uppercase tracking-wider mb-2 flex items-center gap-2">
            Hiperparámetros
            {origin === "hp_search" && (
              <span className="px-1.5 py-0.5 rounded text-[9px] font-bold bg-purple-500/20 text-purple-400 leading-none normal-case">
                Optimizados con Optuna
              </span>
            )}
          </h4>
          <div className="bg-background/50 border border-border/40 rounded-lg px-3 py-2 font-mono text-[11px] grid grid-cols-2 sm:grid-cols-3 gap-x-4 gap-y-1">
            {Object.entries(params).map(([k, v]) => (
              <div key={k} className="truncate" title={`${k}: ${typeof v === "object" ? JSON.stringify(v) : String(v)}`}>
                <span className="text-muted-foreground">{k}: </span>
                <span className="text-foreground">{typeof v === "object" ? JSON.stringify(v) : String(v)}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Realworld Accuracy + event breakdown (collapsible, collapsed by default) */}
      {metrics.realworld_accuracy != null && (
        <div>
          <button
            type="button"
            onClick={() => setRwOpen((o) => !o)}
            className="w-full bg-accent/10 border border-accent/20 rounded-lg px-3 py-2 flex items-center justify-between mb-2 hover:bg-accent/15 transition-colors"
          >
            <span className="flex items-center gap-2">
              {rwOpen
                ? <ChevronDown size={12} className="text-muted-foreground" />
                : <ChevronRight size={12} className="text-muted-foreground" />}
              <span className="text-xs text-foreground font-medium">Real World Accuracy</span>
            </span>
            <div className="flex items-center gap-2">
              <span className="text-[11px] text-muted-foreground">
                {metrics.realworld_correct}/{metrics.realworld_total} peleas
              </span>
              <span
                className={[
                  "text-lg font-bold",
                  metrics.realworld_accuracy > 0.65 ? "text-accent" : "text-muted-foreground",
                ].join(" ")}
                style={OSWALD}
              >
                {fmtPct(metrics.realworld_accuracy)}
              </span>
            </div>
          </button>

          {rwOpen && rwEvents.length > 0 && (
            <div className="space-y-1">
              {rwEvents.map((ev: RealworldEvent) => {
                const isExp = expanded.has(ev.event);
                const evAcc = ev.total > 0 ? ev.correct / ev.total : 0;
                return (
                  <div key={ev.event} className="rounded-lg border border-border/60 overflow-hidden">
                    <button
                      type="button"
                      onClick={() => toggle(ev.event)}
                      className="w-full flex items-center justify-between px-3 py-1.5 hover:bg-card-hover transition-colors"
                    >
                      <span className="flex items-center gap-2 min-w-0">
                        {isExp
                          ? <ChevronDown size={11} className="text-muted-foreground shrink-0" />
                          : <ChevronRight size={11} className="text-muted-foreground shrink-0" />}
                        {ev.date && (
                          <span className="text-[10px] text-muted-foreground shrink-0 tabular-nums">
                            {ev.date.slice(0, 10)}
                          </span>
                        )}
                        <span className="text-[11px] text-foreground font-medium truncate">{ev.event}</span>
                      </span>
                      <span className="flex items-center gap-2 shrink-0">
                        <span
                          className={[
                            "text-[11px] font-medium",
                            evAcc >= 0.65 ? "text-accent" : evAcc >= 0.5 ? "text-foreground" : "text-destructive",
                          ].join(" ")}
                          style={OSWALD}
                        >
                          {ev.correct}/{ev.total}
                        </span>
                        <span className="text-[10px] text-muted-foreground">{fmtPct(evAcc)}</span>
                      </span>
                    </button>

                    {isExp && (
                      <div className="border-t border-border/40 bg-background/50">
                        {ev.fights.map((fight, i) => (
                          <div
                            key={i}
                            className="flex items-center justify-between px-3 py-1 text-[10px] border-b border-border/20 last:border-0"
                          >
                            <span className="flex items-center gap-1.5 min-w-0">
                              {fight.correct
                                ? <CheckCircle2 size={10} className="text-success shrink-0" />
                                : <XCircle size={10} className="text-destructive shrink-0" />}
                              <span className={["truncate", fight.correct ? "text-foreground" : "text-muted-foreground"].join(" ")}>
                                {fight.fighter_1}<span className="text-muted-foreground mx-1">vs</span>{fight.fighter_2}
                              </span>
                            </span>
                            <span className="text-[10px] text-muted-foreground shrink-0 ml-2">
                              {fight.correct ? (
                                <span className="text-success">{fight.real_winner}</span>
                              ) : (
                                <span>
                                  <span className="text-destructive line-through">{fight.predicted_winner}</span>
                                  {" → "}
                                  <span className="text-success">{fight.real_winner}</span>
                                </span>
                              )}
                            </span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* Valor vs mercado (solo RealWorld, requiere odds) */}
      {metrics.realworld_value && (() => {
        const rv: RealworldValue = metrics.realworld_value;
        const deltaColor = rv.brier_delta < 0 ? "text-success" : "text-destructive";
        return (
          <div>
            <h4 className="text-[11px] text-muted-foreground uppercase tracking-wider mb-2">
              Valor vs mercado
              <span className="ml-2 normal-case text-muted-foreground/70">
                {rv.n_with_odds} peleas con odds
              </span>
            </h4>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-3">
              <div className="bg-background/50 border border-border/40 rounded-lg px-3 py-2">
                <div className="text-[10px] text-muted-foreground uppercase tracking-wider">
                  Toss-up acc ({rv.tossup_n})
                </div>
                <div className="text-lg font-bold" style={OSWALD}>{fmtPct(rv.tossup_accuracy)}</div>
                <div className="text-[10px] text-muted-foreground">
                  edge {rv.tossup_edge != null ? `${rv.tossup_edge >= 0 ? "+" : ""}${(rv.tossup_edge * 100).toFixed(1)}%` : "—"}
                </div>
              </div>
              <div className="bg-background/50 border border-border/40 rounded-lg px-3 py-2">
                <div className="text-[10px] text-muted-foreground uppercase tracking-wider">Upset P / R</div>
                <div className="text-lg font-bold" style={OSWALD}>
                  {fmtPct(rv.upset_precision)} / {fmtPct(rv.upset_recall)}
                </div>
                <div className="text-[10px] text-muted-foreground">
                  {rv.underdog_pick_hits}/{rv.underdog_pick_n} aciertos · {rv.upset_detected}/{rv.upset_total} detectados
                </div>
              </div>
              <div className="bg-background/50 border border-border/40 rounded-lg px-3 py-2">
                <div className="text-[10px] text-muted-foreground uppercase tracking-wider">Δ Brier vs mercado</div>
                <div className={["text-lg font-bold", deltaColor].join(" ")} style={OSWALD}>
                  {rv.brier_delta >= 0 ? "+" : ""}{rv.brier_delta.toFixed(4)}
                </div>
                <div className="text-[10px] text-muted-foreground">
                  modelo {rv.brier_model.toFixed(4)} · casa {rv.brier_market.toFixed(4)}
                </div>
              </div>
            </div>
            <table className="w-full text-[11px]">
              <thead>
                <tr className="text-muted-foreground border-b border-border/30">
                  <th className="text-left py-1 px-2">Bucket (fav no-vig)</th>
                  <th className="text-right py-1 px-2">Peleas</th>
                  <th className="text-right py-1 px-2">Acc modelo</th>
                  <th className="text-right py-1 px-2">% upset real</th>
                </tr>
              </thead>
              <tbody>
                {rv.buckets.map((b) => (
                  <tr key={b.label} className="border-b border-border/10">
                    <td className="py-1 px-2 text-foreground">{b.label}</td>
                    <td className="py-1 px-2 text-right display-num">{b.n}</td>
                    <td className="py-1 px-2 text-right display-num">{fmtPct(b.model_accuracy)}</td>
                    <td className="py-1 px-2 text-right display-num text-muted-foreground">{fmtPct(b.upset_rate)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        );
      })()}
    </div>
  );
}
