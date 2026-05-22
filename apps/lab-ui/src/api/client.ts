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
export type TrainableModel = { short: string; label: string; family: string };
export type VersionInfo = {
  version_idx: number; feature_set: string; artifact_uri: string;
  metrics_json: Record<string, unknown> | null;
  hp_json: Record<string, unknown> | null;
  starred: boolean; was_production: boolean; note: string | null;
};
export type RealworldFight = {
  fighter_1: string; fighter_2: string;
  predicted_winner: string; real_winner: string; correct: boolean;
};
export type RealworldEvent = {
  event: string; correct: number; total: number; fights: RealworldFight[];
};
export type TrainResult = {
  model_short: string; job_label: string; dataset: string | null;
  accuracy: number | null; log_loss: number | null;
  auc: number | null; overfit_gap: number | null;
  n_train: number | null; n_test: number | null; n_features: number | null;
  realworld_accuracy: number | null; realworld_correct: number; realworld_total: number;
  realworld_events: RealworldEvent[];
  feature_importance: { feature: string; importance: number }[];
  version_idx: number | null; version_id: number | null; error: string | null;
};
export type TrainStatus = {
  is_running: boolean; started_at: string | null; finished_at: string | null;
  model_short: string | null; step: string | null;
  pct: number; job_index: number; n_jobs: number; job_label: string | null;
  result_version_id: number | null;
  logs: string[]; results: TrainResult[]; error: string | null;
};
export type TrainJob = {
  model_short: string; dataset?: string; augment?: boolean | null;
  feature_set?: string; feat_type?: string; min_fights?: number; use_pit?: boolean;
};
export type ScrapingStatus = {
  is_running: boolean; started_at: string | null; finished_at: string | null;
  step: string | null; phase: string | null;
  progress_current: number; progress_total: number; log_lines: string[];
  counts: Record<string, number> | null; error: string | null;
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
export type FighterRankingEntry = {
  rank: number; name: string; elo: number;
  has_photo: boolean; photo_url: string;
};
export type RecentFightRecord = {
  result: string; opponent: string; method: string;
  round: string; event: string; event_date: string;
};
export type FighterProfile = {
  name: string;
  stats: Record<string, string | number>;
  n_fights: number;
  career_stats: Record<string, number>;
  elo: number;
  has_photo: boolean;
  photo_url: string;
  recent_fights: RecentFightRecord[];
};
export type FightStatsRecord = {
  fight_index: number;
  result: string;
  opponent: string;
  method: string;
  round: string;
  event: string;
  event_date: string;
  kd_landed: number;
  kd_received: number;
  sig_str_landed: number;
  sig_str_attempted: number;
  sig_str_received: number;
  sig_str_received_attempted: number;
  td_landed: number;
  td_attempted: number;
  td_received: number;
  td_received_attempted: number;
  sub_att: number;
  reversals: number;
  ctrl_seconds: number;
  opp_ctrl_seconds: number;
  head_landed: number;
  body_landed: number;
  leg_landed: number;
  distance_landed: number;
  clinch_landed: number;
  ground_landed: number;
};
export type FightMatchupResponse = {
  fighter: string;
  opponent: string;
  event: string;
  result: string;
  method: string;
  round: string;
  fighter_stats: Record<string, number>;
  opponent_stats: Record<string, number>;
};
export type CompareResp = {
  fighter_a: Fighter & { fight_count: number };
  fighter_b: Fighter & { fight_count: number };
};
export type CompareFighterStats = {
  name: string;
  stats: Record<string, string>;
  career: Record<string, number>;
  elo: number;
  photo_url: string;
};
export type StatComparison = {
  f1_value: number;
  f2_value: number;
  better: "fighter_1" | "fighter_2" | "tie";
};
export type FeatureDelta = {
  feature: string;
  label: string;
  f1_value: number | null;
  f2_value: number | null;
  delta: number;
  better: string;
};
export type RecentFight = {
  fight_index: number;
  result: string;
  opponent: string;
  method: string;
  round: string;
  event: string;
  event_date: string;
};
export type HeadToHeadPrediction = {
  prob_f1: number;
  prob_f2: number;
  models: Record<string, number>;
  contributing_models: string[];
  fighter_1_has_history: boolean;
  fighter_2_has_history: boolean;
};
export type CompareByNameResponse = {
  fighter_1: CompareFighterStats;
  fighter_2: CompareFighterStats;
  stat_comparison: Record<string, StatComparison>;
  prediction: HeadToHeadPrediction | null;
  feature_deltas: FeatureDelta[];
  recent_fights_f1: RecentFight[];
  recent_fights_f2: RecentFight[];
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
  trainable: () => request<TrainableModel[]>("/models/trainable"),
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
  deleteVersionsBatch: (short: string, version_idxs: number[]) =>
    request<{ deleted: number[]; skipped: { version_idx: number; reason: string }[] }>(
      `/models/${short}/versions/delete-batch`,
      { method: "POST", body: JSON.stringify({ version_idxs }) }
    ),
  train: (body: { model_short: string; feature_set?: string; feat_type?: string }) =>
    request<{ started: boolean; message?: string; training_session_id?: number }>(
      "/models/train", { method: "POST", body: JSON.stringify(body) }
    ),
  retrainBatch: (jobs: TrainJob[]) =>
    request<{ started: boolean; message?: string; n_jobs: number }>(
      "/models/retrain/batch", { method: "POST", body: JSON.stringify({ jobs }) }
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
  photoScrapeStart: (limit?: number) =>
    request<{ started: boolean; message: string }>(
      `/scraping/photos${limit ? `?limit=${limit}` : ""}`,
      { method: "POST" }
    ),
  photoScrapeStatus: () => request<ScrapingStatus>("/scraping/photos/status"),

  // hp-search
  hpStart: (body: { model_short: string; feature_set?: string; n_trials?: number }) =>
    request<{ started: boolean; study_id: number | null; message?: string }>(
      "/hp-search/start", { method: "POST", body: JSON.stringify(body) }
    ),
  hpStudies: () => request<HpStudy[]>("/hp-search/studies"),
  hpStatus: () => request<{
    is_running: boolean; study_id: number | null; model_short: string | null;
    completed_trials: number; best_value: number | null; step: string | null;
    started_at: string | null; finished_at: string | null; error: string | null;
  }>("/hp-search/status"),

  // combo-search
  comboStart: (body: { name: string }) =>
    request<{ started: boolean; study_id: number | null; message?: string }>(
      "/combo-search/start", { method: "POST", body: JSON.stringify(body) }
    ),
  comboStudies: () => request<ComboStudy[]>("/combo-search/studies"),
  comboStatus: () => request<{
    is_running: boolean; study_id: number | null; evaluated: number; total: number;
    best_value: number | null; best_shorts: string[] | null; step: string | null;
    started_at: string | null; finished_at: string | null; error: string | null;
  }>("/combo-search/status"),

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
  fighterNames: () => request<string[]>("/fighters/names"),
  fighterRanking: (limit = 20) =>
    request<FighterRankingEntry[]>(`/fighters/ranking?limit=${limit}`),
  fighterByName: (name: string) =>
    request<FighterProfile>(`/fighters/by-name/${encodeURIComponent(name)}`),
  fightHistoryStats: (name: string) =>
    request<FightStatsRecord[]>(`/fighters/by-name/${encodeURIComponent(name)}/fight-history-stats`),
  fightMatchup: (name: string, fightIndex: number) =>
    request<FightMatchupResponse>(`/fighters/by-name/${encodeURIComponent(name)}/fight-matchup/${fightIndex}`),

  // compare
  compare: (a: number, b: number) =>
    request<CompareResp>(`/compare?a=${a}&b=${b}`),
  compareByName: (f1: string, f2: string) =>
    request<CompareByNameResponse>(
      `/compare/by-name?f1=${encodeURIComponent(f1)}&f2=${encodeURIComponent(f2)}`
    ),

  // publish
  publishDryRun: (body: { version_id?: number; all_active?: boolean; skip_data?: boolean; target?: string }) =>
    request<{ rc: number; plan_text: string }>(
      "/publish/dry-run", { method: "POST", body: JSON.stringify(body) }
    ),

  // recalculation
  recalcRun: (event_ids?: number[]) =>
    request<{ started: boolean; message: string | null }>("/recalculation/run", {
      method: "POST",
      body: JSON.stringify({ event_ids: event_ids ?? null }),
    }),
  recalcStatus: () => request<{
    is_running: boolean; started_at: string | null; finished_at: string | null;
    total_events: number; completed_events: number; skipped_events: number;
    step: string | null; error: string | null;
  }>("/recalculation/status"),
  recalcRuns: () => request<Array<{ session_id: number; event_id: number; event_name: string; created_at: string }>>("/recalculation/runs"),
};
