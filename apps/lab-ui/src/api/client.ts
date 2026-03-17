const BASE = "/api";

async function request<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const r = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...opts.headers },
    ...opts,
  });
  if (!r.ok) {
    const text = await r.text();
    throw new Error(`${r.status} ${r.statusText}: ${text}`);
  }
  return r.json() as Promise<T>;
}

export const api = {
  health: () => request<{ status: string; db: string }>("/system/health"),
  registry: () =>
    request<{ models: Record<string, { version_idx: number; feature_set: string; artifact_uri: string; trained_at: string | null } | null> }>(
      "/system/registry"
    ),
  listModels: () =>
    request<Array<{ short: string; family: string; default_feat_type: string; description: string | null; active_version: number | null }>>(
      "/models/"
    ),
  listVersions: (short: string) =>
    request<Array<{ version_idx: number; feature_set: string; artifact_uri: string; starred: boolean; was_production: boolean; note: string | null }>>(
      `/models/${short}/versions`
    ),
  trainStatus: () => request<{ is_running: boolean; step: string | null }>("/models/train/status"),

  scrapingStatus: () => request<{ is_running: boolean; step: string | null }>("/scraping/status"),
  scrapingRuns: () => request<unknown[]>("/scraping/runs"),

  hpStudies: () => request<unknown[]>("/hp-search/studies"),
  comboStudies: () => request<unknown[]>("/combo-search/studies"),

  events: (status?: string) =>
    request<unknown[]>(`/predictions/events${status ? `?status=${status}` : ""}`),

  fighters: (q?: string) =>
    request<unknown[]>(`/fighters/${q ? `?q=${encodeURIComponent(q)}` : ""}`),
};
