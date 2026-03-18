import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { Card, PageHeader, Button, Input, Badge } from "../components/ui";

export default function HpSearchPage() {
  const qc = useQueryClient();
  const [short, setShort] = useState("");
  const [nTrials, setNTrials] = useState("50");
  const studies = useQuery({ queryKey: ["hp-studies"], queryFn: api.hpStudies });
  const status = useQuery({
    queryKey: ["hp-status"],
    queryFn: api.hpStatus,
    refetchInterval: (q) => (q.state.data?.is_running ? 1000 : 5000),
  });
  const start = useMutation({
    mutationFn: () => api.hpStart({ model_short: short, n_trials: Number(nTrials) }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["hp-studies"] });
      qc.invalidateQueries({ queryKey: ["hp-status"] });
    },
  });

  return (
    <div>
      <PageHeader title="HP Search" subtitle="Optuna · LGBM / XGB" />
      <div className="grid grid-cols-[300px_280px_1fr] gap-4">
        <Card>
          <h3 className="font-display text-sm uppercase tracking-widest text-[var(--color-muted)] mb-3">Nueva busqueda</h3>
          <div className="space-y-3">
            <Input placeholder="model_short" value={short} onChange={(e) => setShort(e.target.value)} />
            <Input placeholder="n_trials" type="number" value={nTrials} onChange={(e) => setNTrials(e.target.value)} />
            <Button onClick={() => start.mutate()} disabled={!short}>Lanzar</Button>
            {start.data && !start.data.started && (
              <p className="text-xs text-red-400">{start.data.message ?? "No se pudo iniciar"}</p>
            )}
          </div>
        </Card>
        <Card>
          <h3 className="font-display text-sm uppercase tracking-widest text-[var(--color-muted)] mb-3">Estado actual</h3>
          {status.data?.is_running ? (
            <div className="space-y-2 text-sm">
              <div className="flex justify-between"><span className="text-[var(--color-muted)]">Model</span><span className="font-mono">{status.data.model_short}</span></div>
              <div className="flex justify-between"><span className="text-[var(--color-muted)]">Trials</span><span className="font-mono">{status.data.completed_trials}</span></div>
              <div className="flex justify-between"><span className="text-[var(--color-muted)]">Best</span><span className="font-mono">{status.data.best_value?.toFixed(4) ?? "—"}</span></div>
              <div className="text-xs text-[var(--color-muted)]">{status.data.step ?? "—"}</div>
            </div>
          ) : (
            <div className="space-y-2 text-sm">
              <p className="text-[var(--color-muted)]">Idle.</p>
              {status.data?.step && (
                <div className="text-xs text-[var(--color-muted)] font-mono">{status.data.step}</div>
              )}
              {status.data?.best_value != null && (
                <div className="flex justify-between"><span className="text-[var(--color-muted)]">Last best</span><span className="font-mono">{status.data.best_value.toFixed(4)}</span></div>
              )}
            </div>
          )}
        </Card>
        <Card>
          <h3 className="font-display text-sm uppercase tracking-widest text-[var(--color-muted)] mb-3">Studies</h3>
          <table className="w-full text-sm">
            <thead className="text-[10px] uppercase tracking-widest text-[var(--color-muted)] border-b border-[var(--color-border)]">
              <tr><th className="text-left py-2">ID</th><th>Model</th><th>FS</th><th>Trials</th><th>Status</th><th>Started</th></tr>
            </thead>
            <tbody>
              {(studies.data ?? []).map((s) => (
                <tr key={s.id} className="border-b border-[var(--color-border)]/40">
                  <td className="py-2 font-mono">{s.id}</td>
                  <td>{s.model_short}</td>
                  <td><Badge tone="muted">{s.feature_set}</Badge></td>
                  <td className="font-mono">{s.n_trials}</td>
                  <td><Badge tone={s.status === "completed" ? "accent" : s.status === "running" ? "gold" : "muted"}>{s.status}</Badge></td>
                  <td className="text-xs text-[var(--color-muted)] font-mono">{s.started_at.slice(0, 16)}</td>
                </tr>
              ))}
              {(studies.data ?? []).length === 0 && (
                <tr><td colSpan={6} className="py-4 text-[var(--color-muted)]">Sin studies.</td></tr>
              )}
            </tbody>
          </table>
        </Card>
      </div>
    </div>
  );
}
