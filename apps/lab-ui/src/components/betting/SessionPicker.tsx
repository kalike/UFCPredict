import { useSessions } from "../predictions/usePredictions";

type Props = {
  value: number | null;
  onChange: (sessionId: number, eventName: string) => void;
};

export function SessionPicker({ value, onChange }: Props) {
  const { data: sessions = [], isLoading } = useSessions();

  return (
    <label className="flex flex-col gap-1 text-xs">
      <span className="text-muted-foreground">Sesión</span>
      <select
        value={value ?? ""}
        disabled={isLoading}
        onChange={(e) => {
          const id = Number(e.target.value);
          const s = sessions.find((x) => x.id === id);
          if (s) onChange(s.id, s.event);
        }}
        className="bg-[var(--color-background)] border border-[var(--color-border)] rounded-md px-3 py-1.5 text-sm focus:border-[var(--color-accent)] focus:outline-none disabled:opacity-50"
      >
        <option value="" disabled>
          {isLoading ? "Cargando…" : "Elige una sesión…"}
        </option>
        {sessions.map((s) => (
          <option key={s.id} value={s.id}>
            {s.event}
            {s.event_date ? ` · ${s.event_date}` : ""} ({s.n_fights} peleas)
          </option>
        ))}
      </select>
    </label>
  );
}
