import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { Card, PageHeader, Button, Badge } from "../components/ui";

export default function RecalculationPage() {
  const qc = useQueryClient();
  const status = useQuery({
    queryKey: ["recalc-status"], queryFn: api.recalcStatus,
    refetchInterval: (q) => (q.state.data?.is_running ? 2000 : 5000),
  });
  const runs = useQuery({ queryKey: ["recalc-runs"], queryFn: api.recalcRuns });
  const run = useMutation({
    mutationFn: () => api.recalcRun(),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["recalc-status"] });
      qc.invalidateQueries({ queryKey: ["recalc-runs"] });
    },
  });

  return (
    <div className="space-y-4">
      <PageHeader title="Recalculation" subtitle="Re-predict eventos completados con modelos activos" />
      <div className="grid grid-cols-[320px_1fr] gap-4">
        <Card>
          <h3 className="font-display text-sm uppercase tracking-widest text-[var(--color-muted)] mb-3">Lanzar</h3>
          <Button onClick={() => run.mutate()} disabled={status.data?.is_running}>
            {status.data?.is_running ? "Corriendo..." : "Run completed events"}
          </Button>
          {run.data?.started === false && (
            <p className="mt-2 text-xs text-[var(--color-accent)]">{run.data.message}</p>
          )}
          <div className="mt-4 space-y-1 text-sm">
            <div className="flex justify-between">
              <span className="text-[var(--color-muted)]">Total</span>
              <span className="display-num font-semibold">{status.data?.total_events ?? 0}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-[var(--color-muted)]">Done</span>
              <span className="display-num font-semibold">{status.data?.completed_events ?? 0}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-[var(--color-muted)]">Skipped</span>
              <span className="display-num font-semibold">{status.data?.skipped_events ?? 0}</span>
            </div>
            <div className="text-xs text-[var(--color-muted)] mt-2">{status.data?.step ?? "—"}</div>
          </div>
        </Card>
        <Card>
          <h3 className="font-display text-sm uppercase tracking-widest text-[var(--color-muted)] mb-3">Runs recientes</h3>
          <table className="w-full text-sm">
            <thead className="text-[10px] uppercase tracking-widest text-[var(--color-muted)] border-b border-[var(--color-border)]">
              <tr><th className="text-left py-2">Session</th><th>Event</th><th>Date</th></tr>
            </thead>
            <tbody>
              {(runs.data ?? []).map(r => (
                <tr key={r.session_id} className="border-b border-[var(--color-border)]/40">
                  <td className="py-2 font-mono">{r.session_id}</td>
                  <td>{r.event_name}</td>
                  <td className="text-xs text-[var(--color-muted)] font-mono">{r.created_at.slice(0, 16)}</td>
                </tr>
              ))}
              {(runs.data ?? []).length === 0 && (
                <tr><td colSpan={3} className="py-4 text-[var(--color-muted)]">Sin runs.</td></tr>
              )}
            </tbody>
          </table>
        </Card>
      </div>
    </div>
  );
}
