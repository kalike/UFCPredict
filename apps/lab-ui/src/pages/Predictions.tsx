import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { Card, PageHeader, Badge } from "../components/ui";

export default function PredictionsPage() {
  const [filter, setFilter] = useState<"all" | "scheduled" | "completed">("all");
  const events = useQuery({
    queryKey: ["events", filter],
    queryFn: () => api.events(filter === "all" ? undefined : filter),
  });

  return (
    <div>
      <PageHeader title="Predictions" subtitle="Eventos disponibles y caches de inferencia" />
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
            <tr><th className="text-left py-2">ID</th><th>Name</th><th>Date</th><th>Status</th><th>Fights</th></tr>
          </thead>
          <tbody>
            {(events.data ?? []).map((e) => (
              <tr key={e.id} className="border-b border-[var(--color-border)]/40">
                <td className="py-2 font-mono">{e.id}</td>
                <td>{e.name}</td>
                <td className="text-xs text-[var(--color-muted)] font-mono">{e.date?.slice(0, 10) ?? "—"}</td>
                <td><Badge tone={e.status === "completed" ? "gold" : "accent"}>{e.status}</Badge></td>
                <td className="font-mono">{e.fight_count}</td>
              </tr>
            ))}
            {(events.data ?? []).length === 0 && (
              <tr><td colSpan={5} className="py-4 text-[var(--color-muted)]">Sin eventos para el filtro.</td></tr>
            )}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
