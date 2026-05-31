import { useState } from "react";
import { Trash2 } from "lucide-react";
import type { HpStudy } from "../../api/client";
import { Badge } from "../ui";
import { useHpTrials } from "./useHpSearch";
import { TrialsTable } from "./TrialsTable";

interface HpStudyResultsProps {
  studies: HpStudy[];
  adopting: boolean;
  liveStudyId: number | null;
  onAdopt: (studyId: number, trialIdxs: number[]) => void;
  onDelete: (studyId: number) => void;
  onDeleteMany: (studyIds: number[]) => void;
}

function statusTone(status: string): "accent" | "gold" | "muted" {
  if (status === "completed") return "accent";
  if (status === "running") return "gold";
  return "muted";
}

function StudyRow({ study, adopting, isLive, isSelected, onSelect, onAdopt, onDelete }: {
  study: HpStudy;
  adopting: boolean;
  isLive: boolean;
  isSelected: boolean;
  onSelect: (studyId: number) => void;
  onAdopt: (studyId: number, trialIdxs: number[]) => void;
  onDelete: (studyId: number) => void;
}) {
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const { data: trials, isLoading } = useHpTrials(open ? study.id : null, false);

  const best = (study.params as { best_value?: number } | null)?.best_value;
  const minFights = (study.params as { min_fights?: number } | null)?.min_fights;
  const canAdopt = study.status === "completed" && !adopting;

  function toggle(idx: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx);
      else next.add(idx);
      return next;
    });
  }

  return (
    <div className="border border-border rounded-lg overflow-hidden">
      {/* Summary row */}
      <div className={`flex items-center transition-colors ${isSelected ? "bg-accent/10" : "hover:bg-card-hover"}`}>
        <span className="pl-3 flex items-center" onClick={(e) => e.stopPropagation()}>
          <input
            type="checkbox"
            checked={isSelected}
            disabled={isLive}
            onChange={() => onSelect(study.id)}
            title={isLive ? "Job en curso" : "Seleccionar para borrado múltiple"}
            className="accent-[var(--color-accent)] cursor-pointer disabled:opacity-30 disabled:cursor-not-allowed"
          />
        </span>
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="flex-1 flex items-center gap-3 px-3 py-2.5 text-left text-sm min-w-0"
        >
          <span className="text-accent w-4">{open ? "▾" : "▸"}</span>
          <span className="font-mono text-muted-foreground w-10">#{study.id}</span>
          <span className="font-semibold text-foreground w-16" style={{ fontFamily: "'Oswald', sans-serif" }}>
            {study.model_short}
          </span>
          <span title="Feature set" className="shrink-0">
            <Badge tone="muted">{study.feature_set}</Badge>
          </span>
          <span title="Feature type" className="text-xs text-muted-foreground font-mono shrink-0">
            {study.feat_type}
          </span>
          <span title="Min fights" className="text-xs text-muted-foreground font-mono shrink-0">
            mf{minFights ?? "?"}
          </span>
          <span className="text-xs text-muted-foreground font-mono shrink-0">{study.n_trials} trials</span>
          <span className="flex-1" />
          {best != null && (
            <span className="text-xs text-muted-foreground">
              best <strong className="text-accent display-num">{(best * 100).toFixed(1)}%</strong>
            </span>
          )}
          <Badge tone={statusTone(study.status)}>{study.status}{isLive ? " ●" : ""}</Badge>
          <span className="text-[11px] text-muted-foreground font-mono w-28 text-right">
            {study.started_at.slice(0, 16).replace("T", " ")}
          </span>
        </button>
        <button
          type="button"
          disabled={isLive}
          title={isLive ? "No se puede eliminar el job en curso" : "Eliminar job"}
          onClick={() => {
            if (window.confirm(`¿Eliminar el job #${study.id} (${study.model_short})? Se borrarán sus ${study.n_trials} trials.`)) {
              onDelete(study.id);
            }
          }}
          className="px-3 self-stretch flex items-center text-muted-foreground hover:text-destructive disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
        >
          <Trash2 size={14} />
        </button>
      </div>

      {/* Expanded: trials + adopt */}
      {open && (
        <div className="px-4 pb-3 space-y-2 border-t border-border/40 pt-3">
          {isLoading && <p className="text-xs text-muted-foreground">Cargando trials…</p>}
          {!isLoading && (trials?.length ?? 0) === 0 && (
            <p className="text-xs text-muted-foreground">Sin trials.</p>
          )}
          {(trials?.length ?? 0) > 0 && (
            <>
              {canAdopt ? (
                selected.size > 0 ? (
                  <div className="flex items-center gap-3">
                    <button
                      type="button"
                      disabled={adopting}
                      onClick={() => { onAdopt(study.id, [...selected]); setSelected(new Set()); }}
                      className="px-3 py-1.5 rounded text-xs font-semibold bg-accent text-accent-foreground hover:bg-accent-hi disabled:opacity-50 transition-colors"
                    >
                      Adoptar {selected.size} trial{selected.size !== 1 ? "s" : ""} → entrenar
                    </button>
                    <button
                      type="button"
                      onClick={() => setSelected(new Set())}
                      className="text-xs text-muted-foreground hover:text-foreground transition-colors"
                    >
                      Limpiar selección
                    </button>
                  </div>
                ) : (
                  <p className="text-[11px] text-muted-foreground">
                    Marca trials con el checkbox para adoptarlos y entrenar el modelo real.
                  </p>
                )
              ) : (
                study.status !== "completed" && (
                  <p className="text-[11px] text-muted-foreground">
                    Solo se pueden adoptar trials de jobs completados.
                  </p>
                )
              )}
              <TrialsTable
                trials={trials ?? []}
                selectable={canAdopt}
                selected={selected}
                onToggle={toggle}
              />
            </>
          )}
        </div>
      )}
    </div>
  );
}

export function HpStudyResults({
  studies, adopting, liveStudyId, onAdopt, onDelete, onDeleteMany,
}: HpStudyResultsProps) {
  const [selectedStudies, setSelectedStudies] = useState<Set<number>>(new Set());

  function toggleStudy(id: number) {
    setSelectedStudies((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  if (studies.length === 0) {
    return <p className="text-sm text-muted-foreground">Sin jobs todavía.</p>;
  }

  const deletable = studies.filter((s) => s.id !== liveStudyId);
  const allSelected = deletable.length > 0 && deletable.every((s) => selectedStudies.has(s.id));

  return (
    <div className="space-y-2">
      {/* Bulk actions */}
      <div className="flex items-center gap-3 text-xs">
        <label className="flex items-center gap-1.5 text-muted-foreground cursor-pointer">
          <input
            type="checkbox"
            checked={allSelected}
            onChange={() =>
              setSelectedStudies(allSelected ? new Set() : new Set(deletable.map((s) => s.id)))
            }
            className="accent-[var(--color-accent)] cursor-pointer"
          />
          Seleccionar todos
        </label>
        {selectedStudies.size > 0 && (
          <>
            <button
              type="button"
              onClick={() => {
                const ids = [...selectedStudies];
                if (window.confirm(`¿Eliminar ${ids.length} job(s) y todos sus trials?`)) {
                  onDeleteMany(ids);
                  setSelectedStudies(new Set());
                }
              }}
              className="inline-flex items-center gap-1.5 px-3 py-1 rounded font-semibold bg-destructive/15 text-destructive border border-destructive/30 hover:bg-destructive/25 transition-colors"
            >
              <Trash2 size={13} /> Eliminar {selectedStudies.size} seleccionado{selectedStudies.size !== 1 ? "s" : ""}
            </button>
            <button
              type="button"
              onClick={() => setSelectedStudies(new Set())}
              className="text-muted-foreground hover:text-foreground transition-colors"
            >
              Limpiar
            </button>
          </>
        )}
      </div>

      {studies.map((s) => (
        <StudyRow
          key={s.id}
          study={s}
          adopting={adopting}
          isLive={s.id === liveStudyId}
          isSelected={selectedStudies.has(s.id)}
          onSelect={toggleStudy}
          onAdopt={onAdopt}
          onDelete={onDelete}
        />
      ))}
    </div>
  );
}
