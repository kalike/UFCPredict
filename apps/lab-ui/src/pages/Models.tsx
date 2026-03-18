import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { Card, PageHeader, Button, Badge } from "../components/ui";

export default function ModelsPage() {
  const [selected, setSelected] = useState<string | null>(null);
  const qc = useQueryClient();
  const models = useQuery({ queryKey: ["models"], queryFn: api.listModels });
  const versions = useQuery({
    queryKey: ["versions", selected],
    queryFn: () => api.listVersions(selected!),
    enabled: !!selected,
  });

  const activate = useMutation({
    mutationFn: ({ short, idx }: { short: string; idx: number }) =>
      api.activate(short, idx),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["models"] });
      qc.invalidateQueries({ queryKey: ["versions", selected] });
    },
  });

  return (
    <div>
      <PageHeader title="Models" subtitle="Registro, versions, activación" />
      <div className="grid grid-cols-[280px_1fr] gap-4">
        <Card>
          <h3 className="font-display text-sm uppercase tracking-widest text-[var(--color-muted)] mb-3">
            Registrados
          </h3>
          {models.isLoading ? <p>…</p> : (
            <ul className="space-y-1">
              {(models.data ?? []).map((m) => (
                <li key={m.short}>
                  <button
                    onClick={() => setSelected(m.short)}
                    className={`w-full text-left px-2 py-1.5 rounded text-sm flex justify-between items-center transition-colors ${
                      selected === m.short ? "bg-[var(--color-accent)]/15 text-[var(--color-accent)]" : "hover:bg-white/5"
                    }`}
                  >
                    <span className="font-mono">{m.short}</span>
                    {m.active_version != null && <Badge tone="accent">v{m.active_version}</Badge>}
                  </button>
                </li>
              ))}
              {(models.data ?? []).length === 0 && (
                <p className="text-sm text-[var(--color-muted)]">Sin modelos. Inserta filas en la tabla <code>model</code> manualmente o vía seed.</p>
              )}
            </ul>
          )}
        </Card>

        <Card>
          <h3 className="font-display text-sm uppercase tracking-widest text-[var(--color-muted)] mb-3">
            Versions {selected && <span className="text-[var(--color-foreground)]">· {selected}</span>}
          </h3>
          {!selected ? (
            <p className="text-sm text-[var(--color-muted)]">Selecciona un modelo a la izquierda.</p>
          ) : versions.isLoading ? <p>…</p> : (
            <table className="w-full text-sm">
              <thead className="text-[10px] uppercase tracking-widest text-[var(--color-muted)] border-b border-[var(--color-border)]">
                <tr>
                  <th className="text-left py-2">v</th>
                  <th className="text-left py-2">FS</th>
                  <th className="text-left py-2">Artifact</th>
                  <th className="text-left py-2">Acción</th>
                </tr>
              </thead>
              <tbody>
                {(versions.data ?? []).map((v) => (
                  <tr key={v.version_idx} className="border-b border-[var(--color-border)]/40">
                    <td className="py-2 font-mono">{v.version_idx}{v.starred && " ★"}</td>
                    <td><Badge tone={v.feature_set === "v7" ? "gold" : "muted"}>{v.feature_set}</Badge></td>
                    <td className="py-2 text-[var(--color-muted)] font-mono text-[11px]">{v.artifact_uri}</td>
                    <td className="py-2">
                      <Button variant="secondary" onClick={() => activate.mutate({ short: selected, idx: v.version_idx })}>
                        Activar
                      </Button>
                    </td>
                  </tr>
                ))}
                {(versions.data ?? []).length === 0 && (
                  <tr><td colSpan={4} className="py-4 text-[var(--color-muted)]">Sin versiones.</td></tr>
                )}
              </tbody>
            </table>
          )}
        </Card>
      </div>
    </div>
  );
}
