import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { Card, PageHeader, Input } from "../components/ui";

export default function FightersPage() {
  const [q, setQ] = useState("");
  const fighters = useQuery({
    queryKey: ["fighters", q],
    queryFn: () => api.fighters(q || undefined),
  });

  return (
    <div>
      <PageHeader title="Fighters" subtitle={`${fighters.data?.length ?? 0} resultados`} />
      <Card>
        <div className="mb-4">
          <Input placeholder="Buscar por nombre…" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        <ul className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
          {(fighters.data ?? []).map((f) => (
            <li key={f.id} className="border border-[var(--color-border)]/40 rounded-md p-3 hover:border-[var(--color-accent)]/50 transition-colors">
              <div className="font-medium">{f.name}</div>
              <div className="text-xs text-[var(--color-muted)] font-mono mt-1">
                {f.record ?? "—"} · {f.stance ?? "?"} · {f.height_cm ? `${f.height_cm}cm` : "?"}
              </div>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}
