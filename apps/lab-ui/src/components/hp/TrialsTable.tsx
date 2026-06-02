import { Fragment, useState } from "react";
import type { HpTrial } from "../../api/client";

interface TrialsTableProps {
  trials: HpTrial[];
  selectable?: boolean;
  selected?: Set<number>;
  onToggle?: (idx: number) => void;
}

const MINIMIZE = new Set(["mean_logloss", "mean_brier", "mean_overfit", "prod_brier"]);

const METRIC_COLS: { key: keyof NonNullable<HpTrial["metrics"]>; label: string; pct: boolean }[] = [
  { key: "mean_accuracy", label: "Acc (CV)", pct: true },
  { key: "mean_train_accuracy", label: "Train Acc", pct: true },
  { key: "prod_accuracy", label: "Prod Acc", pct: true },
  { key: "realworld_accuracy", label: "RW (todos)", pct: true },
  { key: "realworld_mf_accuracy", label: "RW (min_fights)", pct: true },
  { key: "mean_logloss", label: "LogLoss", pct: false },
  { key: "mean_brier", label: "Brier", pct: false },
  { key: "mean_overfit", label: "Overfit", pct: false },
  { key: "mean_auc", label: "AUC", pct: true },
  { key: "tossup_acc_col" as never, label: "Toss-up", pct: true },
  { key: "upset_pr_col" as never, label: "Upset P/R", pct: false },
  { key: "brier_delta_col" as never, label: "ΔBrier", pct: false },
  { key: "roi_all_col" as never, label: "ROI EV+", pct: false },
  { key: "roi_sel_col" as never, label: "EV+ sel", pct: false },
  { key: "roi_val_col" as never, label: "EV+ val", pct: false },
  { key: "roi_dog_all_col" as never, label: "ROI dog", pct: false },
  { key: "roi_dog_sel_col" as never, label: "dog sel", pct: false },
  { key: "roi_dog_val_col" as never, label: "dog val", pct: false },
];

function fmt(v: number | null | undefined, pct: boolean): string {
  if (v == null) return "—";
  return pct ? `${(v * 100).toFixed(1)}%` : v.toFixed(4);
}

function fmtParams(params: Record<string, number | string>): string {
  return Object.entries(params)
    .map(([k, v]) => `${k}=${typeof v === "number" ? (Number.isInteger(v) ? v : v.toFixed(3)) : v}`)
    .join(", ");
}

export function TrialsTable({ trials, selectable = false, selected, onToggle }: TrialsTableProps) {
  const [sortKey, setSortKey] = useState<string>("mean_accuracy");
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  function toggleExpand(idx: number) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx);
      else next.add(idx);
      return next;
    });
  }

  const sortAsc = MINIMIZE.has(sortKey);
  const sorted = [...trials].sort((a, b) => {
    const accessor = (t: HpTrial): number => {
      const rv = t.metrics?.realworld_value;
      if (sortKey === "roi_all_col") return rv?.roi_ev ?? (sortAsc ? Infinity : -Infinity);
      if (sortKey === "roi_sel_col") return rv?.roi_ev_sel ?? (sortAsc ? Infinity : -Infinity);
      if (sortKey === "roi_val_col") return rv?.roi_ev_val ?? (sortAsc ? Infinity : -Infinity);
      if (sortKey === "roi_dog_all_col") return rv?.roi_dog ?? (sortAsc ? Infinity : -Infinity);
      if (sortKey === "roi_dog_sel_col") return rv?.roi_dog_sel ?? (sortAsc ? Infinity : -Infinity);
      if (sortKey === "roi_dog_val_col") return rv?.roi_dog_val ?? (sortAsc ? Infinity : -Infinity);
      return (t.metrics?.[sortKey as keyof NonNullable<HpTrial["metrics"]>] as number) ?? (sortAsc ? Infinity : -Infinity);
    };
    const va = accessor(a);
    const vb = accessor(b);
    return sortAsc ? va - vb : vb - va;
  });
  const colSpan = (selectable ? 1 : 0) + 2 + METRIC_COLS.length;

  if (sorted.length === 0) return null;

  return (
    <div className="max-h-96 overflow-auto border border-border/40 rounded-lg">
      <table className="w-full text-xs">
        <thead className="sticky top-0 bg-card z-10">
          <tr className="text-muted-foreground border-b border-border/30">
            {selectable && <th className="py-1.5 px-1 w-6" />}
            <th className="text-left py-1.5 px-2">#</th>
            <th className="text-left py-1.5 px-2">Params</th>
            {METRIC_COLS.map((c) => (
              <th
                key={c.key}
                className="text-right py-1.5 px-2 cursor-pointer select-none hover:text-foreground transition-colors whitespace-nowrap"
                onClick={() => setSortKey(c.key)}
              >
                <span className={sortKey === c.key ? "text-accent font-bold" : ""}>{c.label}</span>
                {sortKey === c.key && <span className="ml-0.5 text-[10px]">{sortAsc ? "▲" : "▼"}</span>}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.slice(0, 60).map((t) => {
            const folds = t.metrics?.fold_accuracies ?? [];
            const rvBuckets = t.metrics?.realworld_value?.buckets ?? [];
            const canExpand = folds.length > 0 || rvBuckets.length > 0;
            const isOpen = expanded.has(t.trial_idx);
            const isSel = !!selected?.has(t.trial_idx);
            return (
              <Fragment key={t.trial_idx}>
                <tr
                  onClick={canExpand ? () => toggleExpand(t.trial_idx) : undefined}
                  className={[
                    "border-b border-border/10 hover:bg-accent/5",
                    canExpand ? "cursor-pointer" : "",
                    isSel ? "bg-accent/15" : t.metrics?.is_pareto ? "bg-accent/10" : "",
                  ].join(" ")}
                >
                  {selectable && (
                    <td className="py-1.5 px-1" onClick={(e) => e.stopPropagation()}>
                      <input
                        type="checkbox"
                        checked={isSel}
                        onChange={() => onToggle?.(t.trial_idx)}
                        className="accent-[var(--color-accent)] cursor-pointer"
                      />
                    </td>
                  )}
                  <td className="py-1.5 px-2 font-mono whitespace-nowrap">
                    {canExpand && (
                      <span className="mr-1 text-accent" title="Ver detalle">
                        {isOpen ? "▾" : "▸"}
                      </span>
                    )}
                    {t.metrics?.is_pareto && <span className="text-accent mr-0.5" title="Pareto óptimo">★</span>}
                    {t.trial_idx}
                  </td>
                  <td className="py-1.5 px-2 font-mono truncate max-w-[220px]" title={JSON.stringify(t.params)}>
                    {fmtParams(t.params)}
                  </td>
                  {METRIC_COLS.map((c) => {
                    const rv = t.metrics?.realworld_value;
                    if (c.key === ("tossup_acc_col" as never)) {
                      return (
                        <td key={c.key} className="py-1.5 px-2 text-right whitespace-nowrap display-num">
                          {rv ? fmt(rv.tossup_accuracy, true) : "—"}
                          {rv && rv.tossup_n > 0 && (
                            <span className="ml-1 text-[10px] text-muted-foreground">({rv.tossup_n})</span>
                          )}
                        </td>
                      );
                    }
                    if (c.key === ("upset_pr_col" as never)) {
                      return (
                        <td key={c.key} className="py-1.5 px-2 text-right whitespace-nowrap display-num">
                          {rv ? `${fmt(rv.upset_precision, true)} / ${fmt(rv.upset_recall, true)}` : "—"}
                        </td>
                      );
                    }
                    if (c.key === ("brier_delta_col" as never)) {
                      return (
                        <td
                          key={c.key}
                          className={[
                            "py-1.5 px-2 text-right whitespace-nowrap display-num font-medium",
                            rv ? (rv.brier_delta < 0 ? "text-success" : "text-destructive") : "",
                          ].join(" ")}
                        >
                          {rv ? `${rv.brier_delta >= 0 ? "+" : ""}${rv.brier_delta.toFixed(4)}` : "—"}
                        </td>
                      );
                    }
                    if (c.key === ("roi_all_col" as never)) {
                      const r = rv?.roi_ev;
                      const np = rv?.n_picks_ev ?? 0;
                      return (
                        <td key={c.key} className="py-1.5 px-2 text-right whitespace-nowrap display-num">
                          {r != null ? `${r >= 0 ? "+" : ""}${(r * 100).toFixed(1)}%` : "—"}
                          {np > 0 && (
                            <span className="ml-1 text-[10px] text-muted-foreground">({np})</span>
                          )}
                        </td>
                      );
                    }
                    if (c.key === ("roi_sel_col" as never)) {
                      const r = rv?.roi_ev_sel;
                      const np = rv?.n_picks_sel ?? 0;
                      return (
                        <td key={c.key} className="py-1.5 px-2 text-right whitespace-nowrap display-num">
                          {r != null ? `${r >= 0 ? "+" : ""}${(r * 100).toFixed(1)}%` : "—"}
                          {np > 0 && (
                            <span className="ml-1 text-[10px] text-muted-foreground">({np})</span>
                          )}
                        </td>
                      );
                    }
                    if (c.key === ("roi_val_col" as never)) {
                      const r = rv?.roi_ev_val;
                      const np = rv?.n_picks_val ?? 0;
                      const small = np > 0 && np < 40;
                      const title = [
                        `n=${np}`,
                        rv?.split_date ? `corte ${rv.split_date}` : null,
                        small ? "muestra pequeña" : null,
                      ].filter(Boolean).join(" · ");
                      return (
                        <td
                          key={c.key}
                          title={title}
                          className={[
                            "py-1.5 px-2 text-right whitespace-nowrap display-num font-medium",
                            r != null ? (r > 0 ? "text-success" : r < 0 ? "text-destructive" : "") : "",
                          ].join(" ")}
                        >
                          {r != null ? `${r >= 0 ? "+" : ""}${(r * 100).toFixed(1)}%` : "—"}
                          {np > 0 && (
                            <span className="ml-1 text-[10px] text-muted-foreground">({np})</span>
                          )}
                        </td>
                      );
                    }
                    if (c.key === ("roi_dog_all_col" as never)) {
                      const r = rv?.roi_dog;
                      const np = rv?.n_picks_dog ?? 0;
                      return (
                        <td key={c.key} className="py-1.5 px-2 text-right whitespace-nowrap display-num">
                          {r != null ? `${r >= 0 ? "+" : ""}${(r * 100).toFixed(1)}%` : "—"}
                          {np > 0 && (
                            <span className="ml-1 text-[10px] text-muted-foreground">({np})</span>
                          )}
                        </td>
                      );
                    }
                    if (c.key === ("roi_dog_sel_col" as never)) {
                      const r = rv?.roi_dog_sel;
                      const np = rv?.n_picks_dog_sel ?? 0;
                      return (
                        <td key={c.key} className="py-1.5 px-2 text-right whitespace-nowrap display-num">
                          {r != null ? `${r >= 0 ? "+" : ""}${(r * 100).toFixed(1)}%` : "—"}
                          {np > 0 && (
                            <span className="ml-1 text-[10px] text-muted-foreground">({np})</span>
                          )}
                        </td>
                      );
                    }
                    if (c.key === ("roi_dog_val_col" as never)) {
                      const r = rv?.roi_dog_val;
                      const np = rv?.n_picks_dog_val ?? 0;
                      const small = np > 0 && np < 40;
                      const title = [
                        `n=${np}`,
                        rv?.split_date ? `corte ${rv.split_date}` : null,
                        small ? "muestra pequeña" : null,
                      ].filter(Boolean).join(" · ");
                      return (
                        <td
                          key={c.key}
                          title={title}
                          className={[
                            "py-1.5 px-2 text-right whitespace-nowrap display-num font-medium",
                            r != null ? (r > 0 ? "text-success" : r < 0 ? "text-destructive" : "") : "",
                          ].join(" ")}
                        >
                          {r != null ? `${r >= 0 ? "+" : ""}${(r * 100).toFixed(1)}%` : "—"}
                          {np > 0 && (
                            <span className="ml-1 text-[10px] text-muted-foreground">({np})</span>
                          )}
                        </td>
                      );
                    }
                    if (c.key === "realworld_accuracy" || c.key === "realworld_mf_accuracy") {
                      const isMf = c.key === "realworld_mf_accuracy";
                      const acc = isMf ? t.metrics?.realworld_mf_accuracy : t.metrics?.realworld_accuracy;
                      const corr = (isMf ? t.metrics?.realworld_mf_correct : t.metrics?.realworld_correct) ?? 0;
                      const tot = (isMf ? t.metrics?.realworld_mf_total : t.metrics?.realworld_total) ?? 0;
                      return (
                        <td key={c.key} className="py-1.5 px-2 text-right whitespace-nowrap text-accent-2">
                          <span className="font-medium display-num">{fmt(acc, true)}</span>
                          {tot > 0 && (
                            <span className="ml-1 text-[10px] text-muted-foreground display-num">
                              {corr}/{tot}
                            </span>
                          )}
                        </td>
                      );
                    }
                    return (
                      <td
                        key={c.key}
                        className={[
                          "py-1.5 px-2 text-right font-medium whitespace-nowrap display-num",
                          c.key === "mean_train_accuracy" ? "text-muted-foreground" : "",
                        ].join(" ")}
                      >
                        {fmt(t.metrics?.[c.key] as number | null, c.pct)}
                      </td>
                    );
                  })}
                </tr>
                {isOpen && canExpand && (
                  <tr className="bg-background/40 border-b border-border/10">
                    <td colSpan={colSpan} className="py-2 px-4 space-y-2">
                      {folds.length > 0 && (
                        <div className="flex flex-wrap gap-2">
                          <span className="text-[10px] uppercase tracking-wider text-muted-foreground self-center mr-1">
                            Accuracy por fold (validación temporal):
                          </span>
                          {folds.map((f, i) => (
                            <span
                              key={i}
                              className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md bg-card border border-border text-[11px]"
                              title={`${f.n_val} peleas de validación`}
                            >
                              <span className="text-muted-foreground font-mono">{f.label}</span>
                              <span className="display-num font-semibold text-foreground">
                                {(f.accuracy * 100).toFixed(1)}%
                              </span>
                              {f.train_accuracy != null && (
                                <span className="display-num text-muted-foreground">
                                  (train {(f.train_accuracy * 100).toFixed(1)}%)
                                </span>
                              )}
                            </span>
                          ))}
                        </div>
                      )}
                      {rvBuckets.length > 0 && (
                        <div>
                          <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
                            Valor por bucket de odds (RealWorld):
                          </span>
                          <table className="w-full text-[11px] mt-1">
                            <thead>
                              <tr className="text-muted-foreground border-b border-border/30">
                                <th className="text-left py-0.5 px-2">Bucket (fav no-vig)</th>
                                <th className="text-right py-0.5 px-2">Peleas</th>
                                <th className="text-right py-0.5 px-2">Acc modelo</th>
                                <th className="text-right py-0.5 px-2">% upset real</th>
                              </tr>
                            </thead>
                            <tbody>
                              {rvBuckets.map((b) => (
                                <tr key={b.label} className="border-b border-border/10">
                                  <td className="py-0.5 px-2 text-foreground">{b.label}</td>
                                  <td className="py-0.5 px-2 text-right display-num">{b.n}</td>
                                  <td className="py-0.5 px-2 text-right display-num">
                                    {b.model_accuracy != null ? `${(b.model_accuracy * 100).toFixed(1)}%` : "—"}
                                  </td>
                                  <td className="py-0.5 px-2 text-right display-num text-muted-foreground">
                                    {b.upset_rate != null ? `${(b.upset_rate * 100).toFixed(1)}%` : "—"}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      )}
                    </td>
                  </tr>
                )}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
