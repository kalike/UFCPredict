import { useState } from "react";
import type { UserBet } from "../../api/client";
import { Card, Skeleton } from "../ui";
import { useMyBets, useMyBetsStats, useUpdateBet, useDeleteBet } from "./useMyBets";
import { MyBetsStats } from "./MyBetsStats";
import { MyBetsTable } from "./MyBetsTable";
import { BetEditDialog } from "./BetEditDialog";

export function MyBetsView() {
  const { data: bets = [], isLoading } = useMyBets();
  const { data: stats } = useMyBetsStats();
  const update = useUpdateBet();
  const del = useDeleteBet();
  const [editing, setEditing] = useState<UserBet | null>(null);

  return (
    <div className="space-y-6">
      {stats ? (
        <MyBetsStats stats={stats} />
      ) : (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-20" />
          ))}
        </div>
      )}

      {isLoading ? (
        <Card>
          <Skeleton className="h-40" />
        </Card>
      ) : (
        <MyBetsTable
          bets={bets}
          onEdit={(b) => setEditing(b)}
          onDelete={(b) => {
            if (confirm(`¿Eliminar la apuesta de ${b.event_name ?? "este evento"}?`)) del.mutate(b.id);
          }}
        />
      )}

      <BetEditDialog
        bet={editing}
        open={editing != null}
        onClose={() => setEditing(null)}
        onSave={async (patch) => {
          if (editing) await update.mutateAsync({ id: editing.id, patch });
        }}
      />
    </div>
  );
}
