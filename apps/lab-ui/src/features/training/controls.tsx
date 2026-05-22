import { useState } from "react";

/** Multi-select chip toggle. `value` is the set of selected keys. */
export function ChipToggle<T extends string>({
  options, value, onChange,
}: {
  options: { key: T; label: string }[];
  value: Set<T>;
  onChange: (next: Set<T>) => void;
}) {
  const toggle = (k: T) => {
    const next = new Set(value);
    next.has(k) ? next.delete(k) : next.add(k);
    onChange(next);
  };
  return (
    <div className="flex flex-wrap gap-1.5">
      {options.map((o) => {
        const on = value.has(o.key);
        return (
          <button
            key={o.key}
            type="button"
            onClick={() => toggle(o.key)}
            className={`px-2.5 py-1 rounded-md text-xs font-medium border transition-colors ${
              on
                ? "bg-[var(--color-accent)]/20 text-[var(--color-accent)] border-[var(--color-accent)]/40"
                : "bg-card border-[var(--color-border)] text-[var(--color-muted)] hover:text-[var(--color-foreground)]"
            }`}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

/** A list of integer chips the user can add/remove (e.g. min_fights values). */
export function NumberChips({
  value, onChange, min = 0, max = 20, placeholder = "+",
}: {
  value: number[];
  onChange: (next: number[]) => void;
  min?: number;
  max?: number;
  placeholder?: string;
}) {
  const [draft, setDraft] = useState("");
  const add = () => {
    const n = parseInt(draft, 10);
    if (Number.isNaN(n) || n < min || n > max || value.includes(n)) return;
    onChange([...value, n].sort((a, b) => a - b));
    setDraft("");
  };
  const remove = (n: number) => {
    if (value.length <= 1) return;
    onChange(value.filter((v) => v !== n));
  };
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {value.map((n) => (
        <span
          key={n}
          className="inline-flex items-center gap-1 px-2 py-1 rounded-md text-xs font-mono bg-[var(--color-accent)]/15 text-[var(--color-accent)] border border-[var(--color-accent)]/30"
        >
          {n}
          {value.length > 1 && (
            <button type="button" onClick={() => remove(n)} className="opacity-70 hover:opacity-100">
              ×
            </button>
          )}
        </span>
      ))}
      <input
        type="number"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), add())}
        placeholder={placeholder}
        className="w-16 bg-[var(--color-background)] border border-[var(--color-border)] rounded-md px-2 py-1 text-xs focus:border-[var(--color-accent)] focus:outline-none"
      />
      <button
        type="button"
        onClick={add}
        className="px-2 py-1 rounded-md text-xs bg-white/5 hover:bg-white/10 text-[var(--color-muted)]"
      >
        +
      </button>
    </div>
  );
}

export function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-[10px] uppercase tracking-widest text-[var(--color-muted)] mb-1.5">
        {label}
      </label>
      {children}
      {hint && <p className="mt-1 text-[10px] text-[var(--color-muted)]/70">{hint}</p>}
    </div>
  );
}
