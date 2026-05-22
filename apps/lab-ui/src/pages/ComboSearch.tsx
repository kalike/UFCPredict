import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { Card, PageHeader, Button, Input, Badge } from "../components/ui";

export default function ComboSearchPage() {
  const qc = useQueryClient();
  const [name, setName] = useState("");

  const studies = useQuery({ queryKey: ["combo-studies"], queryFn: api.comboStudies });

  const status = useQuery({
    queryKey: ["combo-status"],
    queryFn: api.comboStatus,
    refetchInterval: (q) => (q.state.data?.is_running ? 1000 : 5000),
  });

  const start = useMutation({
    mutationFn: () => api.comboStart({ name }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["combo-studies"] });
      qc.invalidateQueries({ queryKey: ["combo-status"] });
    },
  });

  const pct = status.data && status.data.total > 0
    ? Math.round((status.data.evaluated / status.data.total) * 100)
    : null;

  return (
    <div>
      <PageHeader title="Combo Search" subtitle="Combinaciones model x version · ensemble accuracy" />
      <div className="grid grid-cols-[300px_280px_1fr] gap-4">
        <Card>
          <h3 className="font-display text-sm uppercase tracking-widest text-[var(--color-muted)] mb-3">Nuevo study</h3>
          <div className="space-y-3">
            <Input placeholder="name (unico)" value={name} onChange={(e) => setName(e.target.value)} />
            <Button onClick={() => start.mutate()} disabled={!name}>Lanzar</Button>
            {start.data?.started === false && (
              <p className="text-xs text-[var(--color-accent)]">{start.data.message}</p>
            )}
          </div>
        </Card>

        <Card>
          <h3 className="font-display text-sm uppercase tracking-widest text-[var(--color-muted)] mb-3">Estado actual</h3>
          {status.data?.is_running ? (
            <div className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-[var(--color-muted)]">Combos</span>
                <span className="display-num font-semibold">{status.data.evaluated} / {status.data.total}</span>
              </div>
              {pct !== null && (
                <div className="w-full bg-[var(--color-border)] rounded-full h-1.5">
                  <div
                    className="bg-[var(--color-accent)] h-1.5 rounded-full transition-all"
                    style={{ width: `${pct}%` }}
                  />
                </div>
              )}
              <div className="flex justify-between">
                <span className="text-[var(--color-muted)]">Best acc</span>
                <span className="display-num font-semibold">{status.data.best_value?.toFixed(4) ?? "—"}</span>
              </div>
              {status.data.best_shorts && (
                <div className="flex flex-wrap gap-1">
                  {status.data.best_shorts.map((s) => (
                    <Badge key={s} tone="gold">{s}</Badge>
                  ))}
                </div>
              )}
              <div className="text-xs text-[var(--color-muted)]">{status.data.step ?? "—"}</div>
            </div>
          ) : (
            <div className="space-y-2 text-sm">
              <p className="text-[var(--color-muted)]">Idle.</p>
              {status.data?.step && (
                <div className="text-xs text-[var(--color-muted)] font-mono">{status.data.step}</div>
              )}
              {status.data?.best_value != null && (
                <div className="flex justify-between">
                  <span className="text-[var(--color-muted)]">Last best</span>
                  <span className="display-num font-semibold">{status.data.best_value.toFixed(4)}</span>
                </div>
              )}
              {status.data?.best_shorts && (
                <div className="flex flex-wrap gap-1">
                  {status.data.best_shorts.map((s) => (
                    <Badge key={s} tone="gold">{s}</Badge>
                  ))}
                </div>
              )}
              {status.data?.error && (
                <p className="text-xs text-red-400 font-mono">{status.data.error}</p>
              )}
            </div>
          )}
        </Card>

        <Card>
          <h3 className="font-display text-sm uppercase tracking-widest text-[var(--color-muted)] mb-3">Studies</h3>
          <table className="w-full text-sm">
            <thead className="text-[10px] uppercase tracking-widest text-[var(--color-muted)] border-b border-[var(--color-border)]">
              <tr>
                <th className="text-left py-2">ID</th>
                <th>Name</th>
                <th>Status</th>
                <th>Best</th>
                <th>Started</th>
              </tr>
            </thead>
            <tbody>
              {(studies.data ?? []).map((s) => (
                <tr key={s.id} className="border-b border-[var(--color-border)]/40">
                  <td className="py-2 font-mono">{s.id}</td>
                  <td>{s.name}</td>
                  <td>
                    <Badge tone={
                      s.status === "completed" ? "accent" :
                      s.status === "running" ? "gold" :
                      s.status === "failed" ? "accent" : "muted"
                    }>
                      {s.status}
                    </Badge>
                  </td>
                  <td className="font-mono text-xs">
                    {(s.params as { best_value?: number } | null)?.best_value?.toFixed(4) ?? "—"}
                  </td>
                  <td className="text-xs text-[var(--color-muted)] font-mono">{s.started_at.slice(0, 16)}</td>
                </tr>
              ))}
              {(studies.data ?? []).length === 0 && (
                <tr><td colSpan={5} className="py-4 text-[var(--color-muted)]">Sin studies.</td></tr>
              )}
            </tbody>
          </table>
        </Card>
      </div>
    </div>
  );
}
