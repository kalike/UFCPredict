import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";

export default function DashboardPage() {
  const health = useQuery({ queryKey: ["health"], queryFn: api.health });
  const registry = useQuery({ queryKey: ["registry"], queryFn: api.registry });
  const models = useQuery({ queryKey: ["models"], queryFn: api.listModels });

  return (
    <div className="space-y-6">
      <header>
        <h2 className="font-display text-3xl tracking-wide uppercase">Dashboard</h2>
        <p className="text-sm text-[var(--color-muted)]">Estado del Lab y modelos registrados.</p>
      </header>

      <section className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-card)] p-5">
          <div className="text-[10px] uppercase tracking-widest text-[var(--color-muted)]">API</div>
          <div className="mt-2 display-num text-3xl font-bold">
            {health.isLoading ? "…" : health.data?.status === "ok" ? "OK" : "ERR"}
          </div>
        </div>
        <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-card)] p-5">
          <div className="text-[10px] uppercase tracking-widest text-[var(--color-muted)]">DB</div>
          <div className="mt-2 display-num text-3xl font-bold">
            {health.isLoading ? "…" : health.data?.db?.startsWith("ok") ? "OK" : "ERR"}
          </div>
        </div>
        <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-card)] p-5">
          <div className="text-[10px] uppercase tracking-widest text-[var(--color-muted)]">Modelos</div>
          <div className="mt-2 display-num text-3xl font-bold">
            {models.isLoading ? "…" : models.data?.length ?? 0}
          </div>
        </div>
      </section>

      <section className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-card)] p-5">
        <h3 className="font-display text-lg tracking-wide uppercase mb-3">Registro</h3>
        {registry.isLoading ? (
          <p className="text-[var(--color-muted)]">Cargando…</p>
        ) : (
          <div className="text-sm">
            {Object.entries(registry.data?.models ?? {}).length === 0 ? (
              <p className="text-[var(--color-muted)]">Sin modelos registrados.</p>
            ) : (
              <ul className="space-y-1">
                {Object.entries(registry.data?.models ?? {}).map(([short, info]) => (
                  <li key={short} className="flex justify-between border-b border-[var(--color-border)] py-1">
                    <span>{short}</span>
                    <span className="text-[var(--color-muted)]">
                      {info ? `v${info.version_idx} · ${info.feature_set}` : "inactive"}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </section>
    </div>
  );
}
