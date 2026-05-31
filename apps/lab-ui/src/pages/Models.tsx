import { Fragment, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Pencil, Star, Trash2, X } from "lucide-react";
import { api } from "../api/client";
import type { ModelInfo, VersionInfo } from "../api/client";
import { PageHeader } from "../components/ui";

const MODEL_COLORS: Record<string, string> = {
  RF35: "#ef4444",
  RFda: "#f97316",
  LGBM: "#22c55e",
  LG52: "#16a34a",
  RF52: "#3b82f6",
  MLP:  "#a855f7",
  SVMb: "#06b6d4",
  SVMg: "#84cc16",
  SVMr: "#f59e0b",
  Deep: "#ec4899",
  RNet: "#14b8a6",
  XGB:  "#8b5cf6",
  XG52: "#6d28d9",
  CB:   "#0ea5e9",
  CB52: "#0284c7",
  LR:   "#d946ef",
  LR52: "#c026d3",
  MLP2: "#fb923c",
  ML52: "#ea580c",
  Ens3: "#ffffff",
};

function modelColor(short: string): string {
  return MODEL_COLORS[short] ?? "#888888";
}

function fmtPct(v: number | null | undefined): string {
  return v != null ? `${(v * 100).toFixed(1)}%` : "—";
}

function metricNum(metrics: Record<string, unknown> | null, key: string): number | null {
  const v = metrics?.[key];
  return typeof v === "number" ? v : null;
}

function fsBadgeClass(fs: string | null): string {
  switch (fs) {
    case "v7": return "bg-teal-500/15 text-teal-400";
    case "v6": return "bg-cyan-500/15 text-cyan-400";
    case "v5": return "bg-purple-500/15 text-purple-400";
    case "v3": return "bg-green-500/15 text-green-400";
    case "v2": return "bg-accent/15 text-accent";
    default:   return "bg-border/50 text-muted-foreground";
  }
}

function ModelCard({
  model, isSelected, onSelect,
}: {
  model: ModelInfo; isSelected: boolean; onSelect: () => void;
}) {
  const accentColor = modelColor(model.short);
  const isActive = model.active_version != null;

  return (
    <div
      onClick={onSelect}
      className={[
        "bg-card border rounded-xl p-4 cursor-pointer hover:bg-card-hover card-hover-glow transition-all duration-200 relative overflow-hidden",
        isSelected ? "border-accent ring-1 ring-accent/30" : "border-border hover:border-border-hover",
      ].join(" ")}
    >
      <div
        className="absolute left-0 top-0 bottom-0 w-[3px] rounded-l-xl"
        style={{ backgroundColor: accentColor }}
      />

      <div className="pl-2">
        <div className="flex items-center justify-between mb-1">
          <span
            className="font-semibold text-foreground text-sm tracking-wide"
            style={{ fontFamily: "'Oswald', sans-serif" }}
          >
            {model.short}
          </span>
          {isActive ? (
            <span className="px-1.5 py-0.5 rounded text-[9px] font-bold bg-green-500/20 text-green-400 leading-none">
              ACTIVO
            </span>
          ) : (
            <span className="px-1.5 py-0.5 rounded text-[9px] font-bold bg-border/50 text-muted-foreground leading-none">
              OFF
            </span>
          )}
        </div>

        <p className="text-xs text-muted truncate mb-3" title={model.description ?? undefined}>
          {model.description ?? model.family}
        </p>

        <div className="flex items-end gap-2 mb-3">
          <span
            className={[
              "text-2xl font-bold leading-none",
              isActive ? "text-accent" : "text-muted-foreground",
            ].join(" ")}
            style={{ fontFamily: "'Oswald', sans-serif" }}
          >
            {isActive ? `v${model.active_version}` : "—"}
          </span>
          <span className="text-xs text-muted-foreground mb-0.5">
            versión activa
          </span>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-[10px] bg-border/50 rounded px-1.5 py-0.5 text-muted-foreground">
            {model.family}
          </span>
          <span className="text-[10px] text-muted-foreground ml-auto">
            {model.default_feat_type}
          </span>
        </div>
      </div>
    </div>
  );
}

function MetricRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-border/40 last:border-0">
      <span className="text-xs text-muted-foreground uppercase tracking-wider">{label}</span>
      <span
        className="text-lg text-foreground font-bold"
        style={{ fontFamily: "'Oswald', sans-serif" }}
      >
        {value}
      </span>
    </div>
  );
}

function ModelDetail({ model, onClose }: { model: ModelInfo; onClose: () => void }) {
  const qc = useQueryClient();
  const short = model.short;
  const accentColor = modelColor(short);
  const [editingNoteIdx, setEditingNoteIdx] = useState<number | null>(null);
  const [noteDraft, setNoteDraft] = useState("");

  const versions = useQuery({
    queryKey: ["versions", short],
    queryFn: () => api.listVersions(short),
  });

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["models"] });
    qc.invalidateQueries({ queryKey: ["versions", short] });
  };

  const activate = useMutation({
    mutationFn: (idx: number) => api.activate(short, idx),
    onSuccess: invalidate,
  });
  const disable = useMutation({
    mutationFn: () => api.disable(short),
    onSuccess: invalidate,
  });
  const mark = useMutation({
    mutationFn: ({ idx, patch }: { idx: number; patch: { starred?: boolean; note?: string } }) =>
      api.mark(short, idx, patch),
    onSuccess: invalidate,
  });
  const remove = useMutation({
    mutationFn: (idx: number) => api.deleteVersion(short, idx),
    onSuccess: invalidate,
  });
  const [sel, setSel] = useState<Set<number>>(new Set());
  const removeBatch = useMutation({
    mutationFn: (idxs: number[]) => api.deleteVersionsBatch(short, idxs),
    onSuccess: () => { setSel(new Set()); invalidate(); },
  });
  const toggleSel = (idx: number) => {
    const next = new Set(sel);
    next.has(idx) ? next.delete(idx) : next.add(idx);
    setSel(next);
  };

  const list = versions.data ?? [];
  const deletableIdxs = list
    .filter((v) => v.version_idx !== model.active_version)
    .map((v) => v.version_idx);
  const allSelected = deletableIdxs.length > 0 && deletableIdxs.every((i) => sel.has(i));
  const toggleAll = () => setSel(allSelected ? new Set() : new Set(deletableIdxs));
  const activeVersion = list.find((v) => v.version_idx === model.active_version) ?? null;
  const metricsSource: VersionInfo | null =
    activeVersion ?? (list.length > 0 ? list[list.length - 1] : null);
  const metrics = metricsSource?.metrics_json ?? null;

  const saveNote = (idx: number) => {
    mark.mutate({ idx, patch: { note: noteDraft } });
    setEditingNoteIdx(null);
    setNoteDraft("");
  };

  return (
    <div className="bg-card border border-accent/30 rounded-xl overflow-hidden">
      {/* Header */}
      <div
        className="flex items-center justify-between px-6 py-4 border-b border-border"
        style={{ borderTop: `3px solid ${accentColor}` }}
      >
        <h2
          className="text-foreground text-xl font-semibold"
          style={{ fontFamily: "'Oswald', sans-serif" }}
        >
          {short}
          {model.description && (
            <span className="ml-3 text-sm font-normal text-muted-foreground">{model.description}</span>
          )}
        </h2>
        <div className="flex items-center gap-3">
          {model.active_version != null && (
            <button
              onClick={() => disable.mutate()}
              disabled={disable.isPending}
              className="px-2 py-1 rounded text-[10px] font-bold bg-destructive/15 text-destructive hover:bg-destructive/25 disabled:opacity-50 transition-colors"
            >
              Desactivar modelo
            </button>
          )}
          <button
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground transition-colors p-1 rounded"
          >
            <X size={18} />
          </button>
        </div>
      </div>

      {/* Body */}
      <div className="p-6 space-y-6">
        {versions.isLoading && <p className="text-sm text-muted-foreground">Cargando versiones…</p>}
        {versions.isError && (
          <p className="text-destructive text-sm">
            Error cargando versiones: {(versions.error as Error).message}
          </p>
        )}

        {!versions.isLoading && (
          <>
            {/* Metrics */}
            <div className="grid grid-cols-2 gap-6">
              <div>
                <h3 className="text-xs text-muted-foreground uppercase tracking-wider mb-3">
                  Métricas de Evaluación
                  {metricsSource && (
                    <span className="ml-2 normal-case tracking-normal">
                      (v{metricsSource.version_idx}{metricsSource === activeVersion ? " · activa" : ""})
                    </span>
                  )}
                </h3>
                {metrics ? (
                  <div>
                    <MetricRow label="Accuracy" value={fmtPct(metricNum(metrics, "accuracy"))} />
                    <MetricRow
                      label="Log Loss"
                      value={metricNum(metrics, "log_loss")?.toFixed(4) ?? "—"}
                    />
                    <div className="mt-2 text-xs text-muted-foreground">
                      n_train: {metricNum(metrics, "n_train") ?? "—"} &middot;{" "}
                      n_test: {metricNum(metrics, "n_test") ?? "—"} &middot;{" "}
                      features: {metricNum(metrics, "n_features") ?? "—"}
                    </div>
                  </div>
                ) : (
                  <p className="text-xs text-muted-foreground">Sin métricas disponibles</p>
                )}
              </div>

              <div>
                <h3 className="text-xs text-muted-foreground uppercase tracking-wider mb-3">
                  Información
                </h3>
                <MetricRow label="Familia" value={model.family} />
                <MetricRow label="Feat type" value={model.default_feat_type} />
                <MetricRow
                  label="Versiones"
                  value={String(list.length)}
                />
              </div>
            </div>

            {/* Active version banner */}
            <div className="bg-accent/10 border border-accent/20 rounded-lg px-4 py-3 flex items-center justify-between">
              <span className="text-sm text-foreground font-medium">Versión activa</span>
              <span
                className={[
                  "text-xl font-bold",
                  model.active_version != null ? "text-accent" : "text-muted-foreground",
                ].join(" ")}
                style={{ fontFamily: "'Oswald', sans-serif" }}
              >
                {model.active_version != null ? `v${model.active_version}` : "ninguna"}
              </span>
            </div>

            {/* Versions table */}
            <div>
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-xs text-muted-foreground uppercase tracking-wider">
                  Versiones ({list.length})
                </h3>
                {sel.size > 0 && (
                  <button
                    onClick={() => {
                      if (window.confirm(`¿Eliminar ${sel.size} versión(es) seleccionada(s)?`)) {
                        removeBatch.mutate([...sel]);
                      }
                    }}
                    disabled={removeBatch.isPending}
                    className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded text-[11px] font-bold bg-destructive/20 text-destructive hover:bg-destructive/30 disabled:opacity-50 transition-colors"
                  >
                    <Trash2 size={12} />
                    Borrar {sel.size} seleccionada{sel.size === 1 ? "" : "s"}
                  </button>
                )}
              </div>
              {list.length === 0 ? (
                <p className="text-xs text-muted-foreground py-4 text-center">
                  Sin versiones guardadas
                </p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="border-b border-border text-muted-foreground">
                        <th className="pb-2 pr-2 w-8 text-center font-medium">
                          <input
                            type="checkbox"
                            checked={allSelected}
                            onChange={toggleAll}
                            disabled={deletableIdxs.length === 0}
                            title="Seleccionar todas (excepto la activa)"
                            className="cursor-pointer"
                          />
                        </th>
                        <th className="pb-2 pr-2 w-8 text-center font-medium">
                          <Star size={11} className="inline text-muted-foreground" />
                        </th>
                        <th className="text-left pb-2 pr-3 font-medium">#</th>
                        <th className="text-left pb-2 pr-3 font-medium">FS</th>
                        <th className="text-left pb-2 pr-3 font-medium">Artifact</th>
                        <th className="text-right pb-2 pr-3 font-medium">Test Acc</th>
                        <th className="text-right pb-2 pr-3 font-medium">Log Loss</th>
                        <th className="text-center pb-2 pr-3 font-medium">Activa</th>
                        <th className="text-right pb-2 font-medium">Acciones</th>
                      </tr>
                    </thead>
                    <tbody>
                      {list.map((v) => {
                        const isActive = v.version_idx === model.active_version;
                        const starred = v.starred === true;
                        const note = v.note ?? null;
                        const isEditingNote = editingNoteIdx === v.version_idx;
                        const acc = metricNum(v.metrics_json, "accuracy");
                        const ll = metricNum(v.metrics_json, "log_loss");

                        return (
                          <Fragment key={v.version_idx}>
                            <tr
                              className={[
                                "border-b hover:bg-card-hover transition-colors",
                                sel.has(v.version_idx) ? "bg-destructive/5" : "",
                                starred ? "bg-yellow-500/5 border-yellow-500/30" : "border-border/40",
                              ].join(" ")}
                            >
                              <td className="py-2 pr-2 text-center">
                                <input
                                  type="checkbox"
                                  checked={sel.has(v.version_idx)}
                                  onChange={() => toggleSel(v.version_idx)}
                                  disabled={isActive}
                                  title={isActive ? "No se puede borrar la versión activa" : undefined}
                                  className="cursor-pointer disabled:opacity-30 disabled:cursor-not-allowed"
                                />
                              </td>
                              <td className="py-2 pr-2 text-center">
                                <button
                                  onClick={() => mark.mutate({ idx: v.version_idx, patch: { starred: !starred } })}
                                  disabled={mark.isPending}
                                  className={[
                                    "transition-colors",
                                    starred
                                      ? "text-yellow-400 hover:text-yellow-300"
                                      : "text-muted-foreground/50 hover:text-yellow-400",
                                  ].join(" ")}
                                  title={starred ? "Quitar marca" : "Marcar versión"}
                                >
                                  <Star size={14} fill={starred ? "currentColor" : "none"} />
                                </button>
                              </td>
                              <td className="py-2 pr-3 text-muted-foreground">{v.version_idx}</td>
                              <td className="py-2 pr-3">
                                <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium uppercase ${fsBadgeClass(v.feature_set)}`}>
                                  {v.feature_set ?? "legacy"}
                                </span>
                              </td>
                              <td className="py-2 pr-3 text-muted-foreground font-mono text-[11px]">
                                {v.artifact_uri}
                              </td>
                              <td className="py-2 pr-3 text-right text-foreground font-medium">
                                <span style={{ fontFamily: "'Oswald', sans-serif" }}>{fmtPct(acc)}</span>
                              </td>
                              <td className="py-2 pr-3 text-right text-muted-foreground">
                                {ll != null ? ll.toFixed(4) : "—"}
                              </td>
                              <td className="py-2 pr-3 text-center">
                                {isActive ? (
                                  <span className="inline-flex items-center gap-1">
                                    <CheckCircle2 size={12} className="text-success" />
                                    <span className="px-1.5 py-0.5 rounded text-[9px] font-bold bg-green-500/20 text-green-400 leading-none">PROD</span>
                                  </span>
                                ) : v.was_production ? (
                                  <span className="px-1.5 py-0.5 rounded text-[9px] font-bold bg-yellow-500/20 text-yellow-400 leading-none" title="Antigua versión de producción">Ex-PROD</span>
                                ) : null}
                              </td>
                              <td className="py-2 text-right">
                                <div className="flex items-center justify-end gap-2">
                                  <button
                                    onClick={() => {
                                      setEditingNoteIdx(v.version_idx);
                                      setNoteDraft(note ?? "");
                                    }}
                                    className={[
                                      "transition-colors",
                                      note
                                        ? "text-accent hover:text-accent/80"
                                        : "text-muted-foreground/60 hover:text-foreground",
                                    ].join(" ")}
                                    title={note ? `Nota: ${note}` : "Añadir nota"}
                                  >
                                    <Pencil size={12} />
                                  </button>
                                  {!isActive && (
                                    <button
                                      onClick={() => activate.mutate(v.version_idx)}
                                      disabled={activate.isPending}
                                      className="px-2 py-0.5 rounded text-[10px] font-bold bg-green-500/20 text-green-400 hover:bg-green-500/35 disabled:opacity-50 transition-colors"
                                    >
                                      Activar
                                    </button>
                                  )}
                                  <button
                                    onClick={() => {
                                      if (window.confirm("¿Eliminar versión?")) {
                                        remove.mutate(v.version_idx);
                                      }
                                    }}
                                    disabled={remove.isPending || isActive}
                                    className="text-destructive hover:text-destructive/80 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                                    title={isActive ? "No se puede eliminar la versión activa" : "Eliminar versión"}
                                  >
                                    <Trash2 size={12} />
                                  </button>
                                </div>
                              </td>
                            </tr>
                            {isEditingNote && (
                              <tr className={starred ? "bg-yellow-500/5" : ""}>
                                <td colSpan={9} className="py-2 px-3">
                                  <div className="flex items-center gap-2">
                                    <input
                                      type="text"
                                      value={noteDraft}
                                      onChange={(e) => setNoteDraft(e.target.value.slice(0, 200))}
                                      onKeyDown={(e) => {
                                        if (e.key === "Enter") saveNote(v.version_idx);
                                        else if (e.key === "Escape") {
                                          setEditingNoteIdx(null);
                                          setNoteDraft("");
                                        }
                                      }}
                                      placeholder="Nota para esta versión (max 200)"
                                      autoFocus
                                      className="flex-1 bg-background border border-border rounded px-2 py-1 text-xs text-foreground outline-none focus:border-accent"
                                    />
                                    <button
                                      onClick={() => saveNote(v.version_idx)}
                                      disabled={mark.isPending}
                                      className="px-2 py-1 rounded text-[10px] font-bold bg-accent/20 text-accent hover:bg-accent/30 disabled:opacity-50"
                                    >
                                      Guardar
                                    </button>
                                    <button
                                      onClick={() => {
                                        setEditingNoteIdx(null);
                                        setNoteDraft("");
                                      }}
                                      className="text-xs text-muted-foreground hover:text-foreground"
                                    >
                                      Cancelar
                                    </button>
                                  </div>
                                </td>
                              </tr>
                            )}
                            {!isEditingNote && note && (
                              <tr className={starred ? "bg-yellow-500/5" : ""}>
                                <td colSpan={9} className="py-1 px-3 text-[11px] text-muted-foreground italic">
                                  {note}
                                </td>
                              </tr>
                            )}
                          </Fragment>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

export default function ModelsPage() {
  const [selected, setSelected] = useState<string | null>(null);
  const models = useQuery({ queryKey: ["models"], queryFn: api.listModels });

  const selectedModel = (models.data ?? []).find((m) => m.short === selected) ?? null;

  return (
    <div className="space-y-5">
      <PageHeader title="Models" subtitle="Registro, versiones, activación" />

      {models.isLoading && <p className="text-sm text-muted-foreground">Cargando modelos…</p>}
      {models.isError && (
        <p className="text-destructive text-sm">
          Error cargando modelos: {(models.error as Error).message}
        </p>
      )}

      {models.data && models.data.length === 0 && (
        <p className="text-sm text-muted-foreground">
          Sin modelos. Inserta filas en la tabla <code>model</code> manualmente o vía seed.
        </p>
      )}

      <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
        {(models.data ?? []).map((m) => (
          <ModelCard
            key={m.short}
            model={m}
            isSelected={selected === m.short}
            onSelect={() => setSelected((prev) => (prev === m.short ? null : m.short))}
          />
        ))}
      </div>

      {selectedModel && (
        <ModelDetail
          key={selectedModel.short}
          model={selectedModel}
          onClose={() => setSelected(null)}
        />
      )}
    </div>
  );
}
