import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { api } from "../api/client";
import { Card, PageHeader, Button, Input, Badge } from "../components/ui";

export default function TrainingPage() {
  const [short, setShort] = useState("");
  const [featureSet, setFeatureSet] = useState("v7");
  const status = useQuery({
    queryKey: ["train-status"], queryFn: api.trainStatus,
    refetchInterval: (q) => (q.state.data?.is_running ? 1500 : false),
  });
  const train = useMutation({
    mutationFn: () => api.train({ model_short: short, feature_set: featureSet }),
  });

  return (
    <div>
      <PageHeader title="Training" subtitle="Lanzar entrenamiento + monitor (stub en F2)" />
      <div className="grid grid-cols-[1fr_1fr] gap-4">
        <Card>
          <h3 className="font-display text-sm uppercase tracking-widest text-[var(--color-muted)] mb-4">Nuevo job</h3>
          <div className="space-y-3">
            <div>
              <label className="text-[10px] uppercase tracking-widest text-[var(--color-muted)]">Model short</label>
              <Input value={short} onChange={(e) => setShort(e.target.value)} placeholder="ej. lgbm" />
            </div>
            <div>
              <label className="text-[10px] uppercase tracking-widest text-[var(--color-muted)]">Feature set</label>
              <Input value={featureSet} onChange={(e) => setFeatureSet(e.target.value)} />
            </div>
            <Button onClick={() => train.mutate()} disabled={!short || train.isPending}>
              {train.isPending ? "Lanzando…" : "Train"}
            </Button>
            {train.data && (
              <p className="text-xs text-[var(--color-muted)]">
                {train.data.started ? `Iniciado · session_id=${train.data.training_session_id}` : train.data.message}
              </p>
            )}
          </div>
        </Card>
        <Card>
          <h3 className="font-display text-sm uppercase tracking-widest text-[var(--color-muted)] mb-4">Status</h3>
          {status.isLoading ? <p>…</p> : (
            <div className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-[var(--color-muted)]">Running</span>
                <Badge tone={status.data?.is_running ? "accent" : "muted"}>{status.data?.is_running ? "yes" : "no"}</Badge>
              </div>
              <div className="flex justify-between">
                <span className="text-[var(--color-muted)]">Step</span>
                <span className="font-mono">{status.data?.step ?? "—"}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-[var(--color-muted)]">Model</span>
                <span className="font-mono">{status.data?.model_short ?? "—"}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-[var(--color-muted)]">Started</span>
                <span className="text-[var(--color-muted)] font-mono text-xs">{status.data?.started_at ?? "—"}</span>
              </div>
              {status.data?.error && (
                <p className="mt-2 text-[var(--color-accent)] text-xs">{status.data.error}</p>
              )}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
