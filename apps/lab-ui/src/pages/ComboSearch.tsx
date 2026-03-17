import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { Card, PageHeader, Button, Input, Badge } from "../components/ui";

export default function ComboSearchPage() {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const studies = useQuery({ queryKey: ["combo-studies"], queryFn: api.comboStudies });
  const start = useMutation({
    mutationFn: () => api.comboStart({ name }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["combo-studies"] }),
  });

  return (
    <div>
      <PageHeader title="Combo Search" subtitle="Combinaciones model x version (worker stub)" />
      <div className="grid grid-cols-[300px_1fr] gap-4">
        <Card>
          <h3 className="font-display text-sm uppercase tracking-widest text-[var(--color-muted)] mb-3">Nuevo study</h3>
          <div className="space-y-3">
            <Input placeholder="name (único)" value={name} onChange={(e) => setName(e.target.value)} />
            <Button onClick={() => start.mutate()} disabled={!name}>Lanzar</Button>
            {start.data?.started === false && (
              <p className="text-xs text-[var(--color-accent)]">{start.data.message}</p>
            )}
          </div>
        </Card>
        <Card>
          <h3 className="font-display text-sm uppercase tracking-widest text-[var(--color-muted)] mb-3">Studies</h3>
          <table className="w-full text-sm">
            <thead className="text-[10px] uppercase tracking-widest text-[var(--color-muted)] border-b border-[var(--color-border)]">
              <tr><th className="text-left py-2">ID</th><th>Name</th><th>Status</th><th>Started</th></tr>
            </thead>
            <tbody>
              {(studies.data ?? []).map((s) => (
                <tr key={s.id} className="border-b border-[var(--color-border)]/40">
                  <td className="py-2 font-mono">{s.id}</td>
                  <td>{s.name}</td>
                  <td><Badge tone={s.status === "completed_stub" ? "gold" : "accent"}>{s.status}</Badge></td>
                  <td className="text-xs text-[var(--color-muted)] font-mono">{s.started_at.slice(0, 16)}</td>
                </tr>
              ))}
              {(studies.data ?? []).length === 0 && (
                <tr><td colSpan={4} className="py-4 text-[var(--color-muted)]">Sin studies.</td></tr>
              )}
            </tbody>
          </table>
        </Card>
      </div>
    </div>
  );
}
