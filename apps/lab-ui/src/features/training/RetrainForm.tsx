import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, type TrainJob } from "../../api/client";
import { Card, Button, Badge } from "../../components/ui";
import { ChipToggle, NumberChips, Field } from "./controls";

type DatasetKey = "since2010" | "since2015" | "since2020";
type AugmentKey = "auto" | "on" | "off";
type FeatTypeKey = "auto" | "35f" | "52f";
type FeatureSetKey = "legacy" | "v2" | "v3" | "v4" | "v5" | "v6" | "v7";

const DATASETS: { key: DatasetKey; label: string }[] = [
  { key: "since2010", label: "2010" },
  { key: "since2015", label: "2015" },
  { key: "since2020", label: "2020" },
];
const AUGMENTS: { key: AugmentKey; label: string }[] = [
  { key: "auto", label: "Auto" },
  { key: "on", label: "ON" },
  { key: "off", label: "OFF" },
];
const FEAT_TYPES: { key: FeatTypeKey; label: string }[] = [
  { key: "auto", label: "Auto" },
  { key: "35f", label: "35f" },
  { key: "52f", label: "52f" },
];
const FEATURE_SETS: { key: FeatureSetKey; label: string }[] = [
  { key: "legacy", label: "Legacy" },
  { key: "v2", label: "V2 (+chin/SoS)" },
  { key: "v3", label: "V3 (−redundantes)" },
  { key: "v4", label: "V4 (−reach_in)" },
  { key: "v5", label: "V5 (−noise)" },
  { key: "v6", label: "V6 (+stance)" },
  { key: "v7", label: "V7 (+Tapology)" },
];

const augmentValue = (k: AugmentKey): boolean | null =>
  k === "on" ? true : k === "off" ? false : null;

function jobKey(j: TrainJob): string {
  return [j.model_short, j.dataset, j.augment, j.min_fights, j.feat_type, j.feature_set, j.use_pit].join("·");
}

export function RetrainForm({
  disabled, onLaunch,
}: {
  disabled: boolean;
  onLaunch: (jobs: TrainJob[]) => void;
}) {
  const trainable = useQuery({ queryKey: ["trainable"], queryFn: api.trainable });

  const [models, setModels] = useState<Set<string>>(new Set());
  const [datasets, setDatasets] = useState<Set<DatasetKey>>(new Set(["since2010"]));
  const [augments, setAugments] = useState<Set<AugmentKey>>(new Set(["auto"]));
  const [minFights, setMinFights] = useState<number[]>([0]);
  const [featTypes, setFeatTypes] = useState<Set<FeatTypeKey>>(new Set(["auto"]));
  const [featureSet, setFeatureSet] = useState<FeatureSetKey>("v7");
  const [usePit, setUsePit] = useState(false);
  const [removed, setRemoved] = useState<Set<string>>(new Set());

  // Cartesian product of the multi-select dimensions → one job each.
  const jobs = useMemo<TrainJob[]>(() => {
    const out: TrainJob[] = [];
    for (const model_short of models)
      for (const d of datasets)
        for (const mf of minFights)
          for (const ft of featTypes)
            for (const aug of augments)
              out.push({
                model_short, dataset: d, augment: augmentValue(aug),
                min_fights: mf, feat_type: ft, feature_set: featureSet, use_pit: usePit,
              });
    return out.filter((j) => !removed.has(jobKey(j)));
  }, [models, datasets, minFights, featTypes, augments, featureSet, usePit, removed]);

  const allShorts = (trainable.data ?? []).map((m) => m.short);

  return (
    <Card>
      <h3 className="font-display text-sm uppercase tracking-widest text-[var(--color-muted)] mb-4">
        Reentrenamiento
      </h3>

      <div className="space-y-4">
        {/* Models */}
        <Field label="Modelos">
          <div className="flex items-center justify-between mb-1.5">
            <ChipToggle
              options={(trainable.data ?? []).map((m) => ({ key: m.short, label: `${m.label} (${m.short})` }))}
              value={models}
              onChange={setModels}
            />
          </div>
          <div className="flex gap-2 mt-1">
            <button type="button" onClick={() => setModels(new Set(allShorts))}
              className="text-[10px] uppercase tracking-widest text-[var(--color-accent)] hover:underline">
              Todos
            </button>
            <button type="button" onClick={() => setModels(new Set())}
              className="text-[10px] uppercase tracking-widest text-[var(--color-muted)] hover:underline">
              Ninguno
            </button>
          </div>
        </Field>

        <div className="grid grid-cols-2 gap-4">
          <Field label="Dataset">
            <ChipToggle options={DATASETS} value={datasets} onChange={setDatasets} />
          </Field>
          <Field label="Augmentation" hint="auto / on / off">
            <ChipToggle options={AUGMENTS} value={augments} onChange={setAugments} />
          </Field>
          <Field label="Min. peleas" hint="0–20">
            <NumberChips value={minFights} onChange={setMinFights} min={0} max={20} />
          </Field>
          <Field label="Feat type">
            <ChipToggle options={FEAT_TYPES} value={featTypes} onChange={setFeatTypes} />
          </Field>
        </div>

        <div className="grid grid-cols-2 gap-4 items-end">
          <Field label="Feature set">
            <select
              value={featureSet}
              onChange={(e) => setFeatureSet(e.target.value as FeatureSetKey)}
              className="w-full bg-[var(--color-background)] border border-[var(--color-border)] rounded-md px-3 py-1.5 text-sm focus:border-[var(--color-accent)] focus:outline-none"
            >
              {FEATURE_SETS.map((f) => (
                <option key={f.key} value={f.key}>{f.label}</option>
              ))}
            </select>
          </Field>
          <label className="flex items-center gap-2 text-sm text-[var(--color-foreground)] pb-1.5 cursor-pointer">
            <input type="checkbox" checked={usePit} onChange={(e) => setUsePit(e.target.checked)} />
            Point-in-Time (PIT)
          </label>
        </div>

        {/* Job queue preview */}
        <div>
          <div className="flex items-center justify-between mb-1.5">
            <label className="text-[10px] uppercase tracking-widest text-[var(--color-muted)]">
              Cola de jobs
            </label>
            <Badge tone={jobs.length > 30 ? "gold" : "muted"}>{jobs.length} job{jobs.length === 1 ? "" : "s"}</Badge>
          </div>
          {jobs.length === 0 ? (
            <p className="text-xs text-[var(--color-muted)] py-2">
              Selecciona al menos un modelo para generar jobs.
            </p>
          ) : (
            <div className="max-h-44 overflow-auto rounded-md border border-[var(--color-border)]">
              <table className="w-full text-xs">
                <tbody>
                  {jobs.map((j, i) => (
                    <tr key={jobKey(j)} className="border-b border-[var(--color-border)]/40 hover:bg-white/5">
                      <td className="py-1.5 px-2 text-[var(--color-muted)] w-6">{i + 1}</td>
                      <td className="py-1.5 px-2 font-mono">{j.model_short}</td>
                      <td className="py-1.5 px-2 text-[var(--color-muted)]">
                        {j.dataset} · mf={j.min_fights} · {j.feat_type} ·{" "}
                        {j.augment === true ? "aug" : j.augment === false ? "no-aug" : "aug:auto"}
                      </td>
                      <td className="py-1.5 px-2 text-right">
                        <button
                          type="button"
                          onClick={() => setRemoved(new Set(removed).add(jobKey(j)))}
                          className="text-[var(--color-muted)] hover:text-red-400"
                        >
                          ×
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {jobs.length > 30 && (
            <p className="mt-1 text-[10px] text-[var(--color-gold)]">
              {jobs.length} jobs es mucho — considera reducir combinaciones.
            </p>
          )}
        </div>

        <Button disabled={disabled || jobs.length === 0} onClick={() => onLaunch(jobs)}>
          {disabled ? "En curso…" : `Entrenar ${jobs.length} job${jobs.length === 1 ? "" : "s"}`}
        </Button>
      </div>
    </Card>
  );
}
