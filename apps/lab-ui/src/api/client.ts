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

// ─── Types ───────────────────────────────────────────
export type ModelInfo = {
  short: string; family: string; default_feat_type: string;
  description: string | null; active_version: number | null;
};
export type VersionInfo = {
  version_idx: number; feature_set: string; artifact_uri: string;
  metrics_json: Record<string, unknown> | null;
  hp_json: Record<string, unknown> | null;
  starred: boolean; was_production: boolean; note: string | null;
};
export type TrainStatus = {
  is_running: boolean; started_at: string | null; finished_at: string | null;
  model_short: string | null; step: string | null;
  result_version_id: number | null; error: string | null;
};
export type ScrapingStatus = {
  is_running: boolean; started_at: string | null; finished_at: string | null;
  step: string | null; counts: Record<string, number> | null; error: string | null;
};
export type ScrapingRun = {
  id: number; source: string; started_at: string; finished_at: string | null;
  new_count: number; updated_count: number; error_msg: string | null;
};
export type HpStudy = {
  id: number; model_short: string; feature_set: string; feat_type: string;
  dataset: string; n_trials: number; status: string;
  started_at: string; finished_at: string | null;
  params: Record<string, unknown> | null;
};
export type ComboStudy = {
  id: number; name: string; status: string;
  started_at: string; finished_at: string | null;
  params: Record<string, unknown> | null;
};
export type Event = { id: number; name: string; date: string | null; status: string; fight_count: number };
export type Fighter = {
  id: number; name: string; slug: string;
  record: string | null; stance: string | null;
  height_cm: number | null; reach_cm: number | null;
  photo_url: string | null;
};
export type FighterDetail = Fighter & {
  ufcstats_url: string; tapology_url: string | null; fight_count: number;
};
export type CompareResp = {
  fighter_a: Fighter & { fight_count: number };
  fighter_b: Fighter & { fight_count: number };
};

// ─── API ─────────────────────────────────────────────
export const api = {
  // system
  health: () => request<{ status: string; db: string }>("/system/health"),
  registry: () =>
    request<{ models: Record<string, { version_idx: number; feature_set: string; artifact_uri: string; trained_at: string | null } | null> }>(
      "/system/registry"
    ),

  // models
  listModels: () => request<ModelInfo[]>("/models/"),
  listVersions: (short: string) => request<VersionInfo[]>(`/models/${short}/versions`),
  activate: (short: string, idx: number) =>
    request<{ ok: boolean }>(`/models/${short}/versions/${idx}/activate`, { method: "POST" }),
  disable: (short: string) =>
    request<{ ok: boolean }>(`/models/${short}/disable`, { method: "POST" }),
  mark: (short: string, idx: number, body: { starred?: boolean; note?: string }) =>
    request<{ ok: boolean }>(`/models/${short}/versions/${idx}/mark`, {
      method: "PATCH", body: JSON.stringify(body),
    }),
  deleteVersion: (short: string, idx: number) =>
    request<{ ok: boolean }>(`/models/${short}/versions/${idx}`, { method: "DELETE" }),
  train: (body: { model_short: string; feature_set?: string; feat_type?: string }) =>
    request<{ started: boolean; message?: string; training_session_id?: number }>(
      "/models/train", { method: "POST", body: JSON.stringify(body) }
    ),
  trainStatus: () => request<TrainStatus>("/models/train/status"),

  // scraping
  scrapingStart: (letters?: string) =>
    request<{ started: boolean; message: string }>(
      `/scraping/start${letters ? `?letters=${encodeURIComponent(letters)}` : ""}`,
      { method: "POST" }
    ),
  scrapingStatus: () => request<ScrapingStatus>("/scraping/status"),
  scrapingRuns: () => request<ScrapingRun[]>("/scraping/runs"),

  // hp-search
  hpStart: (body: { model_short: string; feature_set?: string; n_trials?: number }) =>
    request<{ started: boolean; study_id: number | null; message?: string }>(
      "/hp-search/start", { method: "POST", body: JSON.stringify(body) }
    ),
  hpStudies: () => request<HpStudy[]>("/hp-search/studies"),

  // combo-search
  comboStart: (body: { name: string }) =>
    request<{ started: boolean; study_id: number | null; message?: string }>(
      "/combo-search/start", { method: "POST", body: JSON.stringify(body) }
    ),
  comboStudies: () => request<ComboStudy[]>("/combo-search/studies"),

  // predictions
  events: (status?: string) =>
    request<Event[]>(`/predictions/events${status ? `?status=${status}` : ""}`),
  predict: (eventId: number) =>
    request<{ session_id: number; event_id: number; event_name: string; predictions: Array<{ fight_id: number; fighter_1: string; fighter_2: string; prob_f1: number; prob_f2: number; contributing_models: string[] }>; notes: string | null }>(
      `/predictions/event/${eventId}/predict`,
      { method: "POST" }
    ),

  // fighters
  fighters: (q?: string) =>
    request<Fighter[]>(`/fighters/${q ? `?q=${encodeURIComponent(q)}` : ""}`),
  fighter: (id: number) => request<FighterDetail>(`/fighters/${id}`),

  // compare
  compare: (a: number, b: number) =>
    request<CompareResp>(`/compare?a=${a}&b=${b}`),

  // publish
  publishDryRun: (body: { version_id?: number; all_active?: boolean; skip_data?: boolean; target?: string }) =>
    request<{ rc: number; plan_text: string }>(
      "/publish/dry-run", { method: "POST", body: JSON.stringify(body) }
    ),
};
