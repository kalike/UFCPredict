import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { api } from "../api/client";
import { Card, PageHeader, Button, Input } from "../components/ui";

export default function PublishPage() {
  const [versionId, setVersionId] = useState("");
  const [allActive, setAllActive] = useState(false);
  const [target, setTarget] = useState<"aws" | "local">("aws");
  const dryRun = useMutation({
    mutationFn: () => api.publishDryRun({
      version_id: versionId ? Number(versionId) : undefined,
      all_active: allActive,
      target,
    }),
  });

  return (
    <div>
      <PageHeader title="Publish" subtitle="ufc-publish dry-run (real run en F4)" />
      <Card className="mb-4">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-[10px] uppercase tracking-widest text-[var(--color-muted)]">version_id</label>
            <Input value={versionId} onChange={(e) => setVersionId(e.target.value)} disabled={allActive} placeholder="o usa all_active" />
          </div>
          <div>
            <label className="text-[10px] uppercase tracking-widest text-[var(--color-muted)]">target</label>
            <select
              value={target}
              onChange={(e) => setTarget(e.target.value as "aws" | "local")}
              className="w-full bg-[var(--color-background)] border border-[var(--color-border)] rounded-md px-3 py-1.5 text-sm"
            >
              <option value="aws">aws</option>
              <option value="local">local</option>
            </select>
          </div>
          <label className="flex items-center gap-2 text-sm col-span-2">
            <input type="checkbox" checked={allActive} onChange={(e) => setAllActive(e.target.checked)} />
            <span>--all-active</span>
          </label>
          <div className="col-span-2">
            <Button onClick={() => dryRun.mutate()} disabled={!allActive && !versionId}>
              {dryRun.isPending ? "Calculando…" : "Dry Run"}
            </Button>
          </div>
        </div>
      </Card>
      {dryRun.data && (
        <Card>
          <h3 className="font-display text-sm uppercase tracking-widest text-[var(--color-muted)] mb-2">Plan (rc={dryRun.data.rc})</h3>
          <pre className="font-mono text-xs whitespace-pre-wrap text-[var(--color-foreground)] bg-[var(--color-background)] p-3 rounded-md border border-[var(--color-border)]">{dryRun.data.plan_text || "(sin output)"}</pre>
        </Card>
      )}
    </div>
  );
}
