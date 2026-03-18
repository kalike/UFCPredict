import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { Card, PageHeader, Input, Button } from "../components/ui";

export default function ComparePage() {
  const [a, setA] = useState("");
  const [b, setB] = useState("");
  const [pair, setPair] = useState<{ a: number; b: number } | null>(null);
  const cmp = useQuery({
    queryKey: ["compare", pair],
    queryFn: () => api.compare(pair!.a, pair!.b),
    enabled: !!pair,
  });

  return (
    <div>
      <PageHeader title="Compare" subtitle="Head-to-head básico entre dos fighter ids" />
      <Card className="mb-4">
        <div className="grid grid-cols-[1fr_1fr_auto] gap-3 items-end">
          <div>
            <label className="text-[10px] uppercase tracking-widest text-[var(--color-muted)]">Fighter A id</label>
            <Input value={a} onChange={(e) => setA(e.target.value)} placeholder="ej. 1" />
          </div>
          <div>
            <label className="text-[10px] uppercase tracking-widest text-[var(--color-muted)]">Fighter B id</label>
            <Input value={b} onChange={(e) => setB(e.target.value)} placeholder="ej. 2" />
          </div>
          <Button onClick={() => setPair({ a: Number(a), b: Number(b) })} disabled={!a || !b}>Compare</Button>
        </div>
      </Card>
      {cmp.isError && <Card><p className="text-[var(--color-accent)] text-sm">{(cmp.error as Error).message}</p></Card>}
      {cmp.data && (
        <div className="grid grid-cols-2 gap-4">
          {[cmp.data.fighter_a, cmp.data.fighter_b].map((f, i) => (
            <Card key={i}>
              <h3 className="font-display text-2xl tracking-wide">{f.name}</h3>
              <ul className="mt-3 space-y-1 text-sm font-mono">
                <li className="flex justify-between"><span className="text-[var(--color-muted)]">Record</span>{f.record ?? "—"}</li>
                <li className="flex justify-between"><span className="text-[var(--color-muted)]">Stance</span>{f.stance ?? "?"}</li>
                <li className="flex justify-between"><span className="text-[var(--color-muted)]">Height</span>{f.height_cm ?? "?"} cm</li>
                <li className="flex justify-between"><span className="text-[var(--color-muted)]">Reach</span>{f.reach_cm ?? "?"} cm</li>
                <li className="flex justify-between"><span className="text-[var(--color-muted)]">Fights</span>{f.fight_count}</li>
              </ul>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
