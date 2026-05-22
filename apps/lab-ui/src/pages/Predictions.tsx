import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { Card, PageHeader, Badge, Button } from "../components/ui";

export default function PredictionsPage() {
  const [filter, setFilter] = useState<"all" | "scheduled" | "completed">("all");
  const [selectedEvent, setSelectedEvent] = useState<number | null>(null);
  const events = useQuery({
    queryKey: ["events", filter],
    queryFn: () => api.events(filter === "all" ? undefined : filter),
  });
  const predict = useMutation({
    mutationFn: (eventId: number) => api.predict(eventId),
  });

  return (
    <div className="space-y-4">
      <PageHeader title="Predictions" subtitle="Eventos disponibles · ejecuta inference contra los modelos activos" />
      <Card>
        <div className="flex gap-2 mb-4">
          {(["all", "scheduled", "completed"] as const).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-3 py-1 rounded-md text-xs uppercase tracking-widest transition-colors ${
                filter === f ? "bg-[var(--color-accent)] text-white" : "bg-white/5 hover:bg-white/10"
              }`}
            >
              {f}
            </button>
          ))}
        </div>
        <table className="w-full text-sm">
          <thead className="text-[10px] uppercase tracking-widest text-[var(--color-muted)] border-b border-[var(--color-border)]">
            <tr>
              <th className="text-left py-2">ID</th>
              <th className="text-left">Name</th>
              <th>Date</th>
              <th>Status</th>
              <th>Fights</th>
              <th>Acción</th>
            </tr>
          </thead>
          <tbody>
            {(events.data ?? []).map((e) => (
              <tr key={e.id} className="border-b border-[var(--color-border)]/40">
                <td className="py-2 font-mono">{e.id}</td>
                <td>{e.name}</td>
                <td className="text-xs text-[var(--color-muted)] font-mono">{e.date?.slice(0, 10) ?? "—"}</td>
                <td><Badge tone={e.status === "completed" ? "gold" : "accent"}>{e.status}</Badge></td>
                <td className="font-mono">{e.fight_count}</td>
                <td>
                  <Button
                    variant="secondary"
                    onClick={() => { setSelectedEvent(e.id); predict.mutate(e.id); }}
                    disabled={predict.isPending}
                  >
                    {predict.isPending && selectedEvent === e.id ? "Calculando…" : "Predict"}
                  </Button>
                </td>
              </tr>
            ))}
            {(events.data ?? []).length === 0 && (
              <tr><td colSpan={6} className="py-4 text-[var(--color-muted)]">Sin eventos para el filtro.</td></tr>
            )}
          </tbody>
        </table>
      </Card>

      {predict.isError && (
        <Card><p className="text-[var(--color-accent)] text-sm">{(predict.error as Error).message}</p></Card>
      )}

      {predict.data && (
        <Card>
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-display text-sm uppercase tracking-widest text-[var(--color-muted)]">
              {predict.data.event_name} · session #{predict.data.session_id}
            </h3>
            {predict.data.notes && <span className="text-[10px] text-[var(--color-muted)]">{predict.data.notes}</span>}
          </div>
          <table className="w-full text-sm">
            <thead className="text-[10px] uppercase tracking-widest text-[var(--color-muted)] border-b border-[var(--color-border)]">
              <tr><th className="text-left py-2">Fight</th><th>P(F1)</th><th>P(F2)</th><th>Modelos</th></tr>
            </thead>
            <tbody>
              {predict.data.predictions.map((p) => (
                <tr key={p.fight_id} className="border-b border-[var(--color-border)]/40">
                  <td className="py-2">{p.fighter_1} <span className="text-[var(--color-muted)]">vs</span> {p.fighter_2}</td>
                  <td className="display-num font-semibold text-base">{(p.prob_f1 * 100).toFixed(1)}%</td>
                  <td className="display-num font-semibold text-base">{(p.prob_f2 * 100).toFixed(1)}%</td>
                  <td className="text-xs text-[var(--color-muted)] font-mono">{p.contributing_models.join(", ")}</td>
                </tr>
              ))}
              {predict.data.predictions.length === 0 && (
                <tr><td colSpan={4} className="py-4 text-[var(--color-muted)]">No hay predicciones (peleadores sin historia).</td></tr>
              )}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
