import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { Card, PageHeader, Button, Input, Badge } from "../components/ui";

export default function ScrapingPage() {
  const qc = useQueryClient();
  const [letters, setLetters] = useState("");
  const status = useQuery({
    queryKey: ["scraping-status"], queryFn: api.scrapingStatus,
    refetchInterval: (q) => (q.state.data?.is_running ? 2000 : false),
  });
  const runs = useQuery({ queryKey: ["scraping-runs"], queryFn: api.scrapingRuns });
  const start = useMutation({
    mutationFn: () => api.scrapingStart(letters || undefined),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["scraping-status"] });
      qc.invalidateQueries({ queryKey: ["scraping-runs"] });
    },
  });

  return (
    <div>
      <PageHeader title="Scraping" subtitle="UFCStats incremental + audit log" />
      <div className="grid grid-cols-[320px_1fr] gap-4">
        <Card>
          <h3 className="font-display text-sm uppercase tracking-widest text-[var(--color-muted)] mb-3">Lanzar</h3>
          <div className="space-y-3">
            <Input placeholder="letters (opcional, ej. a,b)" value={letters} onChange={(e) => setLetters(e.target.value)} />
            <Button onClick={() => start.mutate()} disabled={status.data?.is_running}>
              {status.data?.is_running ? "Corriendo…" : "Start"}
            </Button>
          </div>
          <div className="mt-4 space-y-1 text-sm">
            <div className="flex justify-between">
              <span className="text-[var(--color-muted)]">Running</span>
              <Badge tone={status.data?.is_running ? "accent" : "muted"}>{status.data?.is_running ? "yes" : "no"}</Badge>
            </div>
            <div className="flex justify-between">
              <span className="text-[var(--color-muted)]">Step</span>
              <span className="font-mono text-xs">{status.data?.step ?? "—"}</span>
            </div>
          </div>
        </Card>
        <Card>
          <h3 className="font-display text-sm uppercase tracking-widest text-[var(--color-muted)] mb-3">Runs recientes</h3>
          <table className="w-full text-sm">
            <thead className="text-[10px] uppercase tracking-widest text-[var(--color-muted)] border-b border-[var(--color-border)]">
              <tr><th className="text-left py-2">ID</th><th>Source</th><th>Started</th><th>New</th><th>Upd</th><th>Error</th></tr>
            </thead>
            <tbody>
              {(runs.data ?? []).map((r) => (
                <tr key={r.id} className="border-b border-[var(--color-border)]/40">
                  <td className="py-2 font-mono">{r.id}</td>
                  <td>{r.source}</td>
                  <td className="text-xs text-[var(--color-muted)] font-mono">{r.started_at.slice(0, 16)}</td>
                  <td className="font-mono">{r.new_count}</td>
                  <td className="font-mono">{r.updated_count}</td>
                  <td className="text-xs text-[var(--color-accent)]">{r.error_msg ?? ""}</td>
                </tr>
              ))}
              {(runs.data ?? []).length === 0 && (
                <tr><td colSpan={6} className="py-4 text-[var(--color-muted)]">Sin runs.</td></tr>
              )}
            </tbody>
          </table>
        </Card>
      </div>
    </div>
  );
}
