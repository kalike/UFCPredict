import { useState, useMemo } from "react";
import { X } from "lucide-react";
import type { TrainableModel, HpObjective } from "../../api/client";

export type HpJob = {
  model: string;
  feature_set: string;
  feat_type: string;
  dataset: string;
  min_fights: number;
  n_trials: number;
  objectives: HpObjective[];
  overfit_penalty: number;
};

interface HpSearchFormProps {
  models: TrainableModel[];
  busy: boolean;
  onLaunch: (jobs: HpJob[]) => void;
}

const OBJECTIVE_OPTIONS = [
  { metric: "accuracy", label: "Accuracy", direction: "maximize" },
  { metric: "logloss", label: "Log-Loss", direction: "minimize" },
  { metric: "brier", label: "Brier", direction: "minimize" },
  { metric: "overfit", label: "Overfit", direction: "minimize" },
] as const;

type FeatureSetOption = "legacy" | "v2" | "v3" | "v4" | "v5" | "v6" | "v7";
type FeatTypeOption = "auto" | "35f" | "52f";
type DatasetOption = "since2010" | "since2015" | "since2020";

const FEATURE_SET_LABELS: Record<FeatureSetOption, string> = {
  legacy: "Legacy", v2: "V2", v3: "V3", v4: "V4", v5: "V5", v6: "V6", v7: "V7",
};
const FEAT_TYPE_LABELS: Record<FeatTypeOption, string> = {
  auto: "Auto", "35f": "35f", "52f": "52f",
};
const DATASET_LABELS: Record<DatasetOption, string> = {
  since2010: "desde 2010", since2015: "desde 2015", since2020: "desde 2020",
};

function ChipToggle<T extends string>({
  options, labels, selected, onChange,
}: {
  options: T[];
  labels: Record<T, string>;
  selected: Set<T>;
  onChange: (next: Set<T>) => void;
}) {
  const toggle = (opt: T) => {
    const next = new Set(selected);
    if (next.has(opt)) {
      if (next.size > 1) next.delete(opt);
    } else {
      next.add(opt);
    }
    onChange(next);
  };
  return (
    <div className="flex flex-wrap gap-1.5">
      {options.map((opt) => (
        <button
          key={opt}
          type="button"
          onClick={() => toggle(opt)}
          className={[
            "px-2.5 py-1 rounded-md text-xs font-medium transition-all cursor-pointer",
            selected.has(opt)
              ? "bg-accent/20 text-accent border border-accent/40"
              : "bg-card border border-border text-muted-foreground hover:text-foreground",
          ].join(" ")}
        >
          {labels[opt]}
        </button>
      ))}
    </div>
  );
}

function NumberChips({
  values, onChange, min = 0, max = 20, placeholder,
}: {
  values: number[];
  onChange: (v: number[]) => void;
  min?: number;
  max?: number;
  placeholder: string;
}) {
  const [inputVal, setInputVal] = useState("");
  const addValue = () => {
    const n = Number(inputVal);
    if (!isNaN(n) && n >= min && n <= max && !values.includes(n)) {
      onChange([...values, n].sort((a, b) => a - b));
    }
    setInputVal("");
  };
  const removeValue = (v: number) => {
    if (values.length > 1) onChange(values.filter((x) => x !== v));
  };
  return (
    <div className="space-y-1.5">
      <div className="flex flex-wrap gap-1.5">
        {values.map((v) => (
          <span
            key={v}
            className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs font-medium bg-accent/20 text-accent border border-accent/40"
          >
            {v}
            {values.length > 1 && (
              <button
                type="button"
                onClick={() => removeValue(v)}
                className="hover:text-destructive transition-colors cursor-pointer"
              >
                <X size={10} />
              </button>
            )}
          </span>
        ))}
      </div>
      <div className="flex gap-1.5">
        <input
          type="number"
          min={min}
          max={max}
          value={inputVal}
          onChange={(e) => setInputVal(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addValue(); } }}
          placeholder={placeholder}
          className="w-24 bg-card border border-border rounded-md px-2 py-1 text-xs text-foreground outline-none focus:border-accent transition-colors"
        />
        <button
          type="button"
          onClick={addValue}
          className="px-2 py-1 rounded-md text-xs font-medium bg-card border border-border text-muted-foreground hover:text-foreground hover:border-accent transition-colors cursor-pointer"
        >
          +
        </button>
      </div>
    </div>
  );
}

export function jobKey(j: HpJob): string {
  return `${j.model}_${j.feature_set}_${j.feat_type}_mf${j.min_fights}_${j.dataset}`;
}

export function HpSearchForm({ models, busy, onLaunch }: HpSearchFormProps) {
  const modelOptions = models.map((m) => m.short).filter((s) => s !== "Ens3");
  const modelLabels = Object.fromEntries(modelOptions.map((s) => [s, s])) as Record<string, string>;

  const [selectedModels, setSelectedModels] = useState<Set<string>>(new Set());
  const [featureSets, setFeatureSets] = useState<Set<FeatureSetOption>>(new Set(["v7"]));
  const [featTypes, setFeatTypes] = useState<Set<FeatTypeOption>>(new Set(["auto"]));
  const [datasets, setDatasets] = useState<Set<DatasetOption>>(new Set(["since2010"]));
  const [minFights, setMinFights] = useState<number[]>([2]);
  const [nTrials, setNTrials] = useState(50);
  const [objectives, setObjectives] = useState<HpObjective[]>([
    { metric: "accuracy", direction: "maximize" },
  ]);
  const [overfitPenalty, setOverfitPenalty] = useState(0);
  const [removedJobs, setRemovedJobs] = useState<Set<string>>(new Set());

  const allJobs = useMemo(() => {
    const seen = new Set<string>();
    const jobs: HpJob[] = [];
    for (const model of selectedModels)
      for (const fs of featureSets)
        for (const ft of featTypes)
          for (const ds of datasets)
            for (const mf of minFights) {
              const job: HpJob = {
                model, feature_set: fs, feat_type: ft,
                dataset: ds, min_fights: mf, n_trials: nTrials, objectives,
                overfit_penalty: overfitPenalty,
              };
              const key = jobKey(job);
              if (seen.has(key)) continue;
              seen.add(key);
              jobs.push(job);
            }
    return jobs;
  }, [selectedModels, featureSets, featTypes, datasets, minFights, nTrials, objectives, overfitPenalty]);

  const activeJobs = allJobs.filter((j) => !removedJobs.has(jobKey(j)));
  const canSubmit = activeJobs.length > 0 && objectives.length > 0 && !busy;
  const totalTrials = activeJobs.reduce((s, j) => s + j.n_trials, 0);

  return (
    <div className="space-y-5">
      <div>
        <label className="block text-xs text-muted-foreground uppercase tracking-wider mb-1.5">Modelos</label>
        <ChipToggle
          options={modelOptions}
          labels={modelLabels}
          selected={selectedModels}
          onChange={(s) => { setSelectedModels(s); setRemovedJobs(new Set()); }}
        />
      </div>

      <div>
        <label className="block text-xs text-muted-foreground uppercase tracking-wider mb-1.5">Feature Sets</label>
        <ChipToggle
          options={["legacy", "v2", "v3", "v4", "v5", "v6", "v7"] as FeatureSetOption[]}
          labels={FEATURE_SET_LABELS}
          selected={featureSets}
          onChange={(s) => { setFeatureSets(s); setRemovedJobs(new Set()); }}
        />
      </div>

      <div>
        <label className="block text-xs text-muted-foreground uppercase tracking-wider mb-1.5">Feature Type</label>
        <ChipToggle
          options={["auto", "35f", "52f"] as FeatTypeOption[]}
          labels={FEAT_TYPE_LABELS}
          selected={featTypes}
          onChange={(s) => { setFeatTypes(s); setRemovedJobs(new Set()); }}
        />
      </div>

      <div>
        <label className="block text-xs text-muted-foreground uppercase tracking-wider mb-1.5">Dataset</label>
        <ChipToggle
          options={["since2010", "since2015", "since2020"] as DatasetOption[]}
          labels={DATASET_LABELS}
          selected={datasets}
          onChange={(s) => { setDatasets(s); setRemovedJobs(new Set()); }}
        />
      </div>

      <div>
        <label className="block text-xs text-muted-foreground uppercase tracking-wider mb-1.5">Min Fights</label>
        <NumberChips
          values={minFights}
          onChange={(v) => { setMinFights(v); setRemovedJobs(new Set()); }}
          min={0}
          max={10}
          placeholder="min_fights"
        />
      </div>

      <div>
        <label className="block text-xs text-muted-foreground uppercase tracking-wider mb-1.5">Trials por job</label>
        <input
          type="number"
          value={nTrials}
          onChange={(e) => setNTrials(Math.max(1, Number(e.target.value)))}
          min={1}
          max={500}
          className="w-full bg-background border border-border rounded-lg px-3 py-2 text-sm"
        />
      </div>

      <div>
        <label className="block text-xs text-muted-foreground uppercase tracking-wider mb-1.5">Objetivos</label>
        <div className="flex flex-wrap gap-x-4 gap-y-1">
          {OBJECTIVE_OPTIONS.map((opt) => {
            const active = objectives.some((o) => o.metric === opt.metric);
            return (
              <label key={opt.metric} className="flex items-center gap-2 text-xs cursor-pointer">
                <input
                  type="checkbox"
                  checked={active}
                  onChange={() => {
                    setObjectives((prev) =>
                      active
                        ? prev.filter((o) => o.metric !== opt.metric)
                        : [...prev, { metric: opt.metric, direction: opt.direction }],
                    );
                    setRemovedJobs(new Set());
                  }}
                  className="accent-[var(--color-accent)]"
                />
                <span className={active ? "text-foreground" : "text-muted-foreground"}>{opt.label}</span>
              </label>
            );
          })}
        </div>
        {objectives.length > 1 && overfitPenalty === 0 && (
          <p className="mt-1 text-[10px] text-muted-foreground">
            Multi-objetivo: Optuna devuelve la frontera de Pareto.
          </p>
        )}
      </div>

      <div>
        <label className="block text-xs text-muted-foreground uppercase tracking-wider mb-1.5">
          Penalización overfit (λ)
        </label>
        <input
          type="number"
          value={overfitPenalty}
          onChange={(e) => { setOverfitPenalty(Math.max(0, Number(e.target.value))); setRemovedJobs(new Set()); }}
          min={0}
          step={0.25}
          className="w-full bg-background border border-border rounded-lg px-3 py-2 text-sm"
        />
        <p className="mt-1 text-[10px] text-muted-foreground">
          {overfitPenalty > 0
            ? `Objetivo único: ${objectives[0]?.metric ?? "accuracy"} − ${overfitPenalty}·overfit (ignora multi-objetivo).`
            : "0 = sin penalización (usa los objetivos de arriba)."}
        </p>
      </div>

      {activeJobs.length > 0 && (
        <div>
          <label className="block text-xs text-muted-foreground uppercase tracking-wider mb-1.5">
            Cola de jobs ({activeJobs.length})
          </label>
          <div className="border border-border/40 rounded-lg overflow-hidden">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-card text-muted-foreground border-b border-border/30">
                  <th className="text-left py-1.5 px-3">Modelo</th>
                  <th className="text-left py-1.5 px-2">Features</th>
                  <th className="text-left py-1.5 px-2">Feat Type</th>
                  <th className="text-left py-1.5 px-2">Min Fights</th>
                  <th className="text-left py-1.5 px-2">Trials</th>
                  <th className="py-1.5 px-2 w-8" />
                </tr>
              </thead>
              <tbody>
                {activeJobs.map((j) => (
                  <tr key={jobKey(j)} className="border-b border-border/10 hover:bg-accent/5">
                    <td className="py-1.5 px-3 font-medium">{j.model}</td>
                    <td className="py-1.5 px-2">
                      <span className="px-1.5 py-0.5 rounded text-[10px] font-medium uppercase bg-accent/15 text-accent">
                        {j.feature_set}
                      </span>
                    </td>
                    <td className="py-1.5 px-2">
                      <span className="px-1.5 py-0.5 rounded text-[10px] font-medium uppercase bg-muted/30 text-muted-foreground">
                        {j.feat_type}
                      </span>
                    </td>
                    <td className="py-1.5 px-2">{j.min_fights}</td>
                    <td className="py-1.5 px-2">{j.n_trials}</td>
                    <td className="py-1.5 px-2">
                      <button
                        type="button"
                        onClick={() => setRemovedJobs((prev) => new Set([...prev, jobKey(j)]))}
                        className="text-muted-foreground hover:text-destructive transition-colors cursor-pointer"
                      >
                        <X size={12} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <button
        type="button"
        disabled={!canSubmit}
        onClick={() => onLaunch(activeJobs)}
        className="w-full py-2.5 rounded-lg text-sm font-semibold bg-accent text-accent-foreground hover:bg-accent-hi transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
      >
        {busy
          ? "Búsqueda en curso…"
          : `Lanzar ${activeJobs.length} búsqueda${activeJobs.length !== 1 ? "s" : ""} (${totalTrials} trials total)`}
      </button>
    </div>
  );
}
