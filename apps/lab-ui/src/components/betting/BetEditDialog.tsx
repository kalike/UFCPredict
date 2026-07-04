import { useEffect, useState } from "react";
import type { UserBet, UserBetStatus } from "../../api/client";
import { Button } from "../ui";

type Patch = Partial<Pick<UserBet, "stake" | "combined_odds" | "status" | "actual_return" | "notes">>;

type Props = {
  bet: UserBet | null;
  open: boolean;
  onClose: () => void;
  onSave: (patch: Patch) => Promise<void>;
};

const STATUSES: UserBetStatus[] = ["pending", "won", "lost", "void", "cashout"];

export function BetEditDialog({ bet, open, onClose, onSave }: Props) {
  const [stake, setStake] = useState("");
  const [odds, setOdds] = useState("");
  const [status, setStatus] = useState<UserBetStatus>("pending");
  const [actualReturn, setActualReturn] = useState("");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (bet) {
      setStake(String(bet.stake));
      setOdds(String(bet.combined_odds));
      setStatus(bet.status);
      setActualReturn(bet.actual_return != null ? String(bet.actual_return) : "");
      setNotes(bet.notes ?? "");
      setError(null);
    }
  }, [bet]);

  if (!bet || !open) return null;

  const handleSave = async () => {
    setError(null);
    if (!stake || isNaN(parseFloat(stake))) {
      setError("Stake inválido");
      return;
    }
    if (!odds || isNaN(parseFloat(odds))) {
      setError("Cuota inválida");
      return;
    }
    const patch: Patch = {
      stake: parseFloat(stake),
      combined_odds: parseFloat(odds),
      status,
      actual_return: actualReturn === "" ? null : parseFloat(actualReturn),
      notes: notes || null,
    };
    if (status === "cashout" && (patch.actual_return == null || isNaN(patch.actual_return))) {
      setError("Cash-out requiere un return manual");
      return;
    }
    if (status === "won" && (patch.actual_return == null || isNaN(patch.actual_return))) {
      patch.actual_return = (patch.stake ?? 0) * (patch.combined_odds ?? 1);
    }
    if (status === "lost") patch.actual_return = 0;
    if (status === "void") patch.actual_return = patch.stake ?? 0;

    try {
      setSaving(true);
      await onSave(patch);
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error al guardar");
    } finally {
      setSaving(false);
    }
  };

  const inputCls =
    "w-full bg-[var(--color-background)] border border-border rounded px-2 py-1.5 text-sm focus:border-[var(--color-accent)] focus:outline-none";

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md rounded-lg border border-border bg-card p-5 space-y-4"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="font-display text-lg uppercase tracking-wide">Editar apuesta</h3>

        <div className="bg-white/5 rounded-lg p-3 text-xs space-y-1">
          <div className="uppercase font-semibold">{bet.bet_type}</div>
          {bet.picks.map((p, i) => (
            <div key={i} className="flex justify-between text-muted-foreground">
              <span>{p.pick}</span>
              <span className="tabular-nums">
                ({p.pick_odds_american > 0 ? "+" : ""}
                {p.pick_odds_american})
              </span>
            </div>
          ))}
        </div>

        <div className="grid grid-cols-2 gap-3">
          <label className="space-y-1 text-xs">
            <span className="text-muted-foreground">Stake (€)</span>
            <input type="number" step="0.01" value={stake} onChange={(e) => setStake(e.target.value)} className={inputCls} />
          </label>
          <label className="space-y-1 text-xs">
            <span className="text-muted-foreground">Cuota combinada</span>
            <input type="number" step="0.01" value={odds} onChange={(e) => setOdds(e.target.value)} className={inputCls} />
          </label>
        </div>

        <label className="space-y-1 block text-xs">
          <span className="text-muted-foreground">Estado</span>
          <select
            value={status}
            onChange={(e) => setStatus(e.target.value as UserBetStatus)}
            className={`${inputCls} capitalize`}
          >
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>

        <label className="space-y-1 block text-xs">
          <span className="text-muted-foreground">
            Return real (€) {status === "cashout" && <span className="text-red-400">*</span>}
          </span>
          <input
            type="number"
            step="0.01"
            value={actualReturn}
            onChange={(e) => setActualReturn(e.target.value)}
            placeholder={
              status === "won"
                ? `Auto: ${(parseFloat(stake || "0") * parseFloat(odds || "1")).toFixed(2)}`
                : ""
            }
            className={inputCls}
          />
        </label>

        <label className="space-y-1 block text-xs">
          <span className="text-muted-foreground">Notas</span>
          <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} className={inputCls} />
        </label>

        {error && <div className="text-xs text-red-400">{error}</div>}

        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            Cancelar
          </Button>
          <Button onClick={handleSave} disabled={saving}>
            {saving ? "Guardando…" : "Guardar"}
          </Button>
        </div>
      </div>
    </div>
  );
}
