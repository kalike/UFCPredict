import { useMemo, useState } from "react";
import { Pencil, Trash2 } from "lucide-react";
import type { UserBet, UserBetStatus } from "../../api/client";

type Props = {
  bets: UserBet[];
  onEdit: (bet: UserBet) => void;
  onDelete: (bet: UserBet) => void;
};

const STATUS_BADGE: Record<UserBetStatus, string> = {
  pending: "bg-white/10 text-muted-foreground",
  won: "bg-emerald-500/15 text-emerald-400",
  lost: "bg-red-500/15 text-red-400",
  void: "bg-sky-500/15 text-sky-400",
  cashout: "bg-violet-500/15 text-violet-400",
};

function betPnl(b: UserBet): number {
  if (b.status === "pending") return 0;
  const ret =
    b.actual_return ??
    (b.status === "won" ? b.stake * b.combined_odds : b.status === "void" ? b.stake : 0);
  return ret - b.stake;
}

export function MyBetsTable({ bets, onEdit, onDelete }: Props) {
  const [eventFilter, setEventFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");

  const events = useMemo(() => {
    const names = new Set<string>();
    bets.forEach((b) => b.event_name && names.add(b.event_name));
    return Array.from(names).sort();
  }, [bets]);

  const filtered = useMemo(
    () =>
      bets.filter((b) => {
        if (eventFilter !== "all" && b.event_name !== eventFilter) return false;
        if (statusFilter !== "all" && b.status !== statusFilter) return false;
        return true;
      }),
    [bets, eventFilter, statusFilter],
  );

  const selectCls =
    "bg-[var(--color-background)] border border-border rounded px-2 py-1 text-xs focus:border-[var(--color-accent)] focus:outline-none";

  return (
    <div className="bg-card border border-border rounded-lg overflow-hidden">
      <div className="flex items-center gap-3 p-4 border-b border-border">
        <h3 className="text-sm font-semibold uppercase tracking-widest text-muted-foreground flex-1">
          Historial ({filtered.length})
        </h3>
        <select value={eventFilter} onChange={(e) => setEventFilter(e.target.value)} className={selectCls}>
          <option value="all">Todos los eventos</option>
          {events.map((e) => (
            <option key={e} value={e}>
              {e}
            </option>
          ))}
        </select>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className={`${selectCls} capitalize`}
        >
          <option value="all">Todos los estados</option>
          {Object.keys(STATUS_BADGE).map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead className="text-muted-foreground">
            <tr className="border-b border-border">
              <th className="text-left p-2 pl-4">Evento</th>
              <th className="text-left p-2">Tipo</th>
              <th className="text-left p-2">Picks</th>
              <th className="text-right p-2">Cuota</th>
              <th className="text-right p-2">Stake</th>
              <th className="text-right p-2">Return</th>
              <th className="text-right p-2">P&amp;L</th>
              <th className="text-left p-2">Estado</th>
              <th className="text-left p-2">Notas</th>
              <th className="p-2 pr-4"></th>
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 && (
              <tr>
                <td colSpan={10} className="p-6 text-center text-muted-foreground">
                  Sin apuestas registradas.
                </td>
              </tr>
            )}
            {filtered.map((b) => {
              const pnl = betPnl(b);
              return (
                <tr key={b.id} className="border-b border-border/40 hover:bg-white/5">
                  <td className="p-2 pl-4 text-foreground">{b.event_name || "—"}</td>
                  <td className="p-2 uppercase text-muted-foreground">{b.bet_type}</td>
                  <td className="p-2">{b.picks.map((p) => p.pick).join(" + ")}</td>
                  <td className="p-2 text-right tabular-nums">{b.combined_odds.toFixed(2)}</td>
                  <td className="p-2 text-right tabular-nums">{b.stake.toFixed(0)}€</td>
                  <td className="p-2 text-right tabular-nums">
                    {b.actual_return != null ? `${b.actual_return.toFixed(0)}€` : "—"}
                  </td>
                  <td
                    className={`p-2 text-right tabular-nums font-semibold ${
                      pnl > 0 ? "text-emerald-400" : pnl < 0 ? "text-red-400" : ""
                    }`}
                  >
                    {b.status === "pending" ? "—" : `${pnl >= 0 ? "+" : ""}${pnl.toFixed(0)}€`}
                  </td>
                  <td className="p-2">
                    <span
                      className={`px-2 py-0.5 rounded text-[10px] uppercase font-semibold ${STATUS_BADGE[b.status]}`}
                    >
                      {b.status}
                    </span>
                  </td>
                  <td className="p-2 text-muted-foreground max-w-[180px] truncate" title={b.notes ?? ""}>
                    {b.notes || ""}
                  </td>
                  <td className="p-2 pr-4">
                    <div className="flex gap-1 justify-end">
                      <button
                        onClick={() => onEdit(b)}
                        className="p-1 rounded hover:bg-white/10 text-muted-foreground hover:text-foreground"
                        title="Editar"
                      >
                        <Pencil size={12} />
                      </button>
                      <button
                        onClick={() => onDelete(b)}
                        className="p-1 rounded hover:bg-red-500/10 text-muted-foreground hover:text-red-400"
                        title="Eliminar"
                      >
                        <Trash2 size={12} />
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
