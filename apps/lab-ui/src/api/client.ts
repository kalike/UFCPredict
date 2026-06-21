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
  trained_at: string | null;
  starred: boolean; was_production: boolean; note: string | null;
};
export type RealworldFight = {
  fighter_1: string; fighter_2: string;
  predicted_winner: string; real_winner: string; correct: boolean;
};
export type RealworldEvent = {
  event: string; date?: string | null; correct: number; total: number; fights: RealworldFight[];
};
export type FeatureImportance = { feature: string; importance: number };
export type RealworldValueBucket = {
  label: string; lo: number; hi: number | null; n: number;
  model_accuracy: number | null; upset_rate: number | null;
};
export type RealworldValue = {
  tossup_threshold: number; n_with_odds: number;
  tossup_n: number; tossup_accuracy: number | null; tossup_edge: number | null;
  underdog_pick_n: number; underdog_pick_hits: number; upset_precision: number | null;
  upset_total: number; upset_detected: number; upset_recall: number | null;
  brier_model: number; brier_market: number; brier_delta: number;
  logloss_model: number; logloss_market: number; logloss_delta: number;
  roi_ev?: number | null; n_picks_ev?: number;
  roi_ev_sel?: number | null; n_picks_sel?: number;
  roi_ev_val?: number | null; n_picks_val?: number;
  roi_dog?: number | null; n_picks_dog?: number;
  roi_dog_sel?: number | null; n_picks_dog_sel?: number;
  roi_dog_val?: number | null; n_picks_dog_val?: number;
  split_date?: string | null;
  buckets: RealworldValueBucket[];
};
// Shape of model_version.metrics_json. All optional: older versions may lack
// the richer pieces (confusion_matrix / feature_importance / realworld_events)
// until backfilled or retrained. Cast metrics_json via asModelMetrics().
export type ModelMetrics = {
  accuracy?: number; precision?: number; recall?: number; f1?: number;
  auc?: number | null; log_loss?: number | null;
  train_accuracy?: number; overfit_gap?: number;
  confusion_matrix?: number[][] | null;
  n_train?: number; n_test?: number; n_features?: number; n_production?: number;
  realworld_accuracy?: number | null; realworld_correct?: number; realworld_total?: number;
  realworld_events?: RealworldEvent[];
  feature_importance?: FeatureImportance[] | null;
  realworld_value?: RealworldValue | null;
};
export function asModelMetrics(m: Record<string, unknown> | null | undefined): ModelMetrics | null {
  return (m ?? null) as ModelMetrics | null;
}
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
export type HpObjective = { metric: string; direction: string };
export type HpFoldAccuracy = { label: string; accuracy: number; train_accuracy: number | null; n_val: number };
export type HpTrialMetrics = {
  mean_accuracy: number | null; mean_train_accuracy: number | null;
  mean_auc: number | null; mean_f1: number | null;
  mean_logloss: number | null; mean_brier: number | null; mean_overfit: number | null;
  prod_accuracy: number | null; prod_brier: number | null;
  fold_accuracies?: HpFoldAccuracy[];
  realworld_accuracy: number | null; realworld_correct: number; realworld_total: number;
  realworld_mf_accuracy?: number | null; realworld_mf_correct?: number;
  realworld_mf_total?: number; realworld_min_fights?: number;
  is_pareto: boolean;
  realworld_value?: RealworldValue | null;
};
export type HpTrial = {
  id: number; study_id: number; trial_idx: number;
  params: Record<string, number | string>; value: number | null;
  metrics: HpTrialMetrics | null; status: string;
};
export type HpStatus = {
  is_running: boolean; study_id: number | null; model_short: string | null;
  completed_trials: number; n_trials: number; best_value: number | null;
  objectives: HpObjective[]; step: string | null;
  started_at: string | null; finished_at: string | null; error: string | null;
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

// ─── Rich predictions ────────────────────────────────
export type ModelPrediction = {
  full_name: string;
  predicted_winner: string;
  probability_f1: number;
  confidence: number;
};
export type Consensus = {
  fighter_1_votes: number;
  fighter_2_votes: number;
  total_models: number;
  consensus_winner: string;
  consensus_pct: number;
};
export type MethodBreakdown = {
  wins: number; losses: number;
  ko_wins: number; sub_wins: number; dec_wins: number;
  ko_losses: number; sub_losses: number; dec_losses: number;
};
export type CommunityMethod = {
  ko_tko_pct: number; submission_pct: number; decision_pct: number;
};
export type CommunityPicks = {
  total_picks: number;
  fighter_1_win_pct: number;
  fighter_2_win_pct: number;
  fighter_1_methods: CommunityMethod;
  fighter_2_methods: CommunityMethod;
};
export type RichFightPrediction = {
  fighter_1: string;
  fighter_2: string;
  event: string;
  odds_f1_american: number | null;
  odds_f2_american: number | null;
  models: Record<string, ModelPrediction>;
  consensus: Consensus | null;
  prob_f1: number;
  prob_f2: number;
  fighter_1_has_history: boolean;
  fighter_2_has_history: boolean;
  fighter_1_n_fights: number;
  fighter_2_n_fights: number;
  fighter_1_methods: MethodBreakdown;
  fighter_2_methods: MethodBreakdown;
  community_picks: CommunityPicks | null;
  real_winner: string | null;
  fight_id: number | null;
  outcome: string | null; // "nc" | "draw" | null
};
export type FightInput = {
  fighter_1: string;
  fighter_2: string;
  odds_f1_american?: number | null;
  odds_f2_american?: number | null;
  community_picks?: CommunityPicks | null;
};
export type PredictResponse = {
  event: string;
  n_fights: number;
  n_models: number;
  fights: RichFightPrediction[];
  skipped: string[];
};
export type PastEventSummary = { name: string; n_fights: number; date: string | null };
export type ModelAccuracy = {
  full_name: string; accuracy: number; correct: number; total: number;
};
export type PastEventPredictions = {
  event: string;
  n_fights: number;
  n_fights_valid: number;
  accuracy: Record<string, ModelAccuracy>;
  fights: RichFightPrediction[];
  skipped: string[];
};
export type SessionFightIn = {
  fighter_1: string;
  fighter_2: string;
  odds_f1_american?: number | null;
  odds_f2_american?: number | null;
  models: Record<string, ModelPrediction>;
  consensus_winner?: string | null;
  consensus_pct?: number | null;
  avg_prob_f1?: number | null;
  community_picks?: CommunityPicks | null;
};
export type SaveSessionRequest = {
  event: string;
  event_date?: string | null;
  fights: SessionFightIn[];
};
export type SessionSummary = {
  id: number;
  event: string;
  created_at: string;
  event_date: string | null;
  n_fights: number;
  n_results: number;
  n_correct: number;
  accuracy: number | null;
  promoted: boolean;
};
export type SessionDetail = {
  id: number;
  event: string;
  created_at: string;
  event_date: string | null;
  n_fights: number;
  promoted: boolean;
  fights: RichFightPrediction[];
};
export type MarkResultResponse = {
  ok: boolean; n_results: number; n_correct: number; accuracy: number | null;
};
export type ImportOddsResponse = {
  ok: boolean; updated: number; updated_fights: string[];
  not_matched: string[]; error: string | null;
};
export type TapologyScrapeFight = {
  fighter_1: string;
  fighter_2: string;
  matchup_url: string;
  odds_f1_american: number | null;
  odds_f2_american: number | null;
  community_picks: CommunityPicks | null;
};
export type TapologyScrapeResponse = {
  event_name: string;
  n_fights: number;
  fights: TapologyScrapeFight[];
  errors: string[];
};
export interface DashModelAccuracy {
  accuracy: number | null;
  correct: number;
  total: number;
}
export interface DashEventAccuracy {
  event: string;
  date: string | null;
  location: string;
  n_fights: number;
  n_fights_valid: number;
  n_correct: number;
  is_past: boolean;
  accuracy_by_model: Record<string, DashModelAccuracy>;
  overall_accuracy: number | null;
}
export interface DashModelAvg {
  avg_accuracy: number | null;
  total_correct: number;
  total_fights: number;
  n_events: number;
}
export interface DashEventFight {
  event: string;
  date: string | null;
  fighter_1: string;
  fighter_2: string;
  predicted_winner: string;
  real_winner: string;
  correct: boolean;
  consensus_pct: number;
}
export interface DashTier {
  correct: number;
  total: number;
  accuracy: number | null;
  label: string;
}
export interface DashSpecialFight {
  event: string;
  date: string | null;
  fighter_1: string;
  fighter_2: string;
  real_winner: string;
  predicted_winner: string;
  correct: boolean;
  fighter_1_dwcs_only: boolean;
  fighter_2_dwcs_only: boolean;
  fighter_1_has_history: boolean;
  fighter_2_has_history: boolean;
}
export interface DashboardSummary {
  latest_event: DashEventAccuracy | null;
  n_predicted_events: number;
  n_past_events: number;
  n_predicted_fights: number;
  n_fighters: number;
  n_models: number;
  models: string[];
  avg_consensus_accuracy: number | null;
  avg_by_model: Record<string, DashModelAvg>;
  accuracy_by_event: DashEventAccuracy[];
  recent_fights: DashEventFight[];
  disabled_models: string[];
  min_fights: number;
  with_odds: boolean;
  consensus_tiers: Record<string, DashTier>;
  probability_tiers: Record<string, DashTier>;
  special_case_tiers: Record<"dwcs_debut" | "no_history" | "combined", DashTier>;
  special_case_fights: DashSpecialFight[];
}
export interface DashRecalcStatus {
  is_running: boolean;
  step: string | null;
  completed_events: number;
  total_events: number;
}

// ─── Betting types ───────────────────────────────────
export interface BettingConfig {
  min_consensus_pct: number;
  min_model_prob: number;
  max_parlay_legs: number;
  kelly_fraction: number;
  max_event_exposure_pct: number;
  max_picks_per_event: number;
  bankroll: number;
  stake_per_combo: number;
  compound_mode?: boolean;
  bankroll_floor?: number;
  parlay_stake_pct?: number;
  min_pit_fights?: number;
  min_prob_leg_double?: number;
  min_prob_leg_triple?: number;
  min_combined_prob_double?: number;
  min_combined_prob_triple?: number;
  min_combo_ev?: number;
  exposure_pct_singles?: number;
  exposure_pct_doubles?: number;
  exposure_pct_triples?: number;
  excluded_picks?: string[];
}

export interface QualifiedPick {
  fighter_1: string;
  fighter_2: string;
  pick: string;
  pick_odds_american: number;
  model_prob: number;
  decimal_odds: number;
  implied_prob: number;
  edge: number;
  ev_per_unit: number;
  kelly_full: number;
  kelly_quarter: number;
  score: number;
  consensus_pct: number;
  excluded: boolean;
  hit: boolean | null;
}

export interface BetCombo {
  type: string;
  picks: QualifiedPick[];
  combined_prob: number;
  combined_odds: number;
  ev: number;
  stake: number;
  potential_return: number;
  hit: boolean | null;
}

export interface RecommendSummary {
  total_stake: number;
  exposure_pct: number;
  n_singles: number;
  n_doubles: number;
  n_triples: number;
  expected_return: number;
}

export interface RecommendResponse {
  event_name: string;
  config: BettingConfig;
  all_qualified_picks: QualifiedPick[];
  qualified_picks: QualifiedPick[];
  singles: BetCombo[];
  doubles: BetCombo[];
  triples: BetCombo[];
  summary: RecommendSummary;
  effective_bankroll?: number | null;
}

export interface ComboDetail {
  type: string;
  pick_names: string[];
  combined_odds: number;
  combined_prob: number;
  ev: number;
  stake: number;
  potential_return: number;
  hit: boolean | null;
}

export interface EventBacktestDetail {
  event_name: string;
  date: string;
  n_qualified: number;
  n_bets: number;
  stake: number;
  returned: number;
  profit: number;
  picks_hit_rate: number;
  picks: { pick: string; odds: number; prob: number; hit: boolean | null; stake?: number | null }[];
  combos: ComboDetail[];
  working_bankroll?: number;
}

export interface StrategyResult {
  total_bets: number;
  total_stake: number;
  total_return: number;
  profit: number;
  roi_pct: number;
  hit_rate_picks: number;
  hit_rate_parlays: number;
  max_drawdown: number;
  sharpe_ratio: number;
  events: EventBacktestDetail[];
  cumulative_pnl: number[];
  bankroll_history?: number[];
}

export interface BacktestResponse {
  config: BettingConfig;
  strategies: Record<string, StrategyResult>;
  total?: StrategyResult | null;
  best_strategy: string;
  total_events: number;
}

export type UserBetStatus = "pending" | "won" | "lost" | "void" | "cashout";

export interface UserBet {
  id: number;
  event_id: number;
  event_name: string | null;
  session_id: number | null;
  bet_type: "single" | "double" | "triple";
  picks: QualifiedPick[];
  combo_key: string;
  combined_odds: number;
  stake: number;
  potential_return: number;
  status: UserBetStatus;
  actual_return: number | null;
  notes: string | null;
  engine_snapshot: BetCombo | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface UserBetsBreakdown {
  bet_type: string;
  n_bets: number;
  n_settled: number;
  stake: number;
  returned: number;
  profit: number;
  roi_pct: number;
  winrate: number;
}

export interface UserBetsStats {
  n_bets: number;
  n_settled: number;
  n_won: number;
  winrate: number;
  total_stake: number;
  total_returned: number;
  net_profit: number;
  roi_pct: number;
  by_type: UserBetsBreakdown[];
  engine_comparison: {
    engine_stake: number;
    engine_returned: number;
    engine_profit: number;
    engine_roi_pct: number;
    delta_roi_pct: number;
  };
}

export type BetConfig = {
  id: number;
  name: string;
  params: { config: Partial<BettingConfig>; combo: Record<string, number> | null };
  is_default: boolean;
  created_at: string | null;
  updated_at: string | null;
};

// ─── API ─────────────────────────────────────────────
export const api = {
  // system
  health: () => request<{ status: string; db: string }>("/system/health"),
  registry: () =>
    request<{ models: Record<string, { version_idx: number; feature_set: string; artifact_uri: string; trained_at: string | null } | null> }>(
      "/system/registry"
    ),
  dashboardSummary: (minFights = 0, withOdds = false) =>
    request<DashboardSummary>(
      `/dashboard/summary?min_fights=${minFights}&with_odds=${withOdds}`
    ),
  dashboardEventFights: (event: string) =>
    request<{ event: string; fights: DashEventFight[] }>(
      `/dashboard/event-fights?event=${encodeURIComponent(event)}`
    ),
  dashboardRecalcStatus: () =>
    request<DashRecalcStatus>("/dashboard/recalculation-status"),
  dashboardInvalidate: (minFights = 0, recalculate = true) =>
    request<{ ok: boolean; recalculating: boolean; message?: string }>(
      `/dashboard/invalidate-cache?recalculate=${recalculate}&min_fights=${minFights}`,
      { method: "POST" }
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
  hpStart: (body: {
    model_short: string;
    feature_set?: string;
    feat_type?: string;
    dataset?: string;
    min_fights?: number;
    n_trials?: number;
    objectives?: HpObjective[];
    overfit_penalty?: number;
  }) =>
    request<{ started: boolean; study_id: number | null; message?: string }>(
      "/hp-search/start", { method: "POST", body: JSON.stringify(body) }
    ),
  hpStudies: () => request<HpStudy[]>("/hp-search/studies"),
  hpTrials: (studyId: number) =>
    request<HpTrial[]>(`/hp-search/studies/${studyId}/trials`),
  hpStatus: () => request<HpStatus>("/hp-search/status"),
  hpAdopt: (items: { study_id: number; trial_idx: number }[]) =>
    request<{ started: boolean; n_jobs: number; message?: string }>(
      "/hp-search/adopt", { method: "POST", body: JSON.stringify({ items }) }
    ),
  hpDeleteStudy: (studyId: number) =>
    request<{ ok: boolean }>(`/hp-search/studies/${studyId}`, { method: "DELETE" }),
  hpDeleteStudiesBatch: (ids: number[]) =>
    request<{ deleted: number; skipped: number[] }>(
      "/hp-search/studies/delete-batch", { method: "POST", body: JSON.stringify({ ids }) }
    ),

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

  // rich predictions — arbitrary matchups
  predictFights: (event_name: string, fights: FightInput[]) =>
    request<PredictResponse>("/predictions/", {
      method: "POST", body: JSON.stringify({ event_name, fights }),
    }),
  tapologyScrape: (url: string) =>
    request<TapologyScrapeResponse>("/predictions/tapology-scrape", {
      method: "POST", body: JSON.stringify({ url }),
    }),

  // past events
  pastEvents: () => request<PastEventSummary[]>("/predictions/past-events"),
  pastEventPredictions: (name: string) =>
    request<PastEventPredictions>(`/predictions/past-events/${encodeURIComponent(name)}`),

  // sessions
  saveSession: (body: SaveSessionRequest) =>
    request<{ ok: boolean; id: number; skipped: string[] }>("/predictions/sessions", {
      method: "POST", body: JSON.stringify(body),
    }),
  listSessions: () => request<SessionSummary[]>("/predictions/sessions"),
  listRealworldSessions: () => request<SessionSummary[]>("/predictions/sessions/realworld"),
  getSession: (id: number) => request<SessionDetail>(`/predictions/sessions/${id}`),
  markResult: (id: number, fight_index: number, real_winner: string | null) =>
    request<MarkResultResponse>(`/predictions/sessions/${id}/result`, {
      method: "PATCH", body: JSON.stringify({ fight_index, real_winner }),
    }),
  deleteSession: (id: number) =>
    request<{ ok: boolean }>(`/predictions/sessions/${id}`, { method: "DELETE" }),
  deleteAllSessions: () =>
    request<{ ok: boolean; deleted: number }>("/predictions/sessions", { method: "DELETE" }),
  promoteSession: (id: number, body: { event_date?: string | null; event_location?: string | null }) =>
    request<{ ok: boolean; event: string; n_fights: number; message: string }>(
      `/predictions/sessions/${id}/promote`, { method: "POST", body: JSON.stringify(body) }
    ),
  importOdds: (id: number, tapology_url: string) =>
    request<ImportOddsResponse>(`/predictions/sessions/${id}/import-odds`, {
      method: "POST", body: JSON.stringify({ tapology_url }),
    }),

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

  // betting
  bettingDefaults: () => request<BettingConfig>("/betting/defaults"),
  runBacktest: (config: BettingConfig) =>
    request<BacktestResponse>("/betting/backtest", { method: "POST", body: JSON.stringify(config) }),
  recommend: (sessionId: number, config: BettingConfig) =>
    request<RecommendResponse>(`/betting/recommend/${sessionId}`, { method: "POST", body: JSON.stringify(config) }),
  listBetConfigs: () => request<BetConfig[]>("/betting/configs"),
  saveBetConfig: (body: { name: string; params: BetConfig["params"]; is_default?: boolean }) =>
    request<BetConfig>("/betting/configs", { method: "POST", body: JSON.stringify(body) }),
  deleteBetConfig: (id: number) =>
    request<{ ok: boolean }>(`/betting/configs/${id}`, { method: "DELETE" }),

  // models combo
  currentCombo: () => request<Record<string, number>>("/models/current-combo"),
  applyCombo: (combo: Record<string, number>) =>
    request<{ applied: unknown[]; skipped: unknown[] }>("/models/apply-combo", { method: "POST", body: JSON.stringify({ combo }) }),

  // user bets
  listUserBets: (params: { event_id?: number; status?: string; bet_type?: string } = {}) => {
    const q = new URLSearchParams(
      Object.entries(params)
        .filter(([, v]) => v != null)
        .map(([k, v]) => [k, String(v)])
    );
    return request<UserBet[]>(`/user-bets${q.toString() ? `?${q}` : ""}`);
  },
  userBetsStats: (eventId?: number) =>
    request<UserBetsStats>(`/user-bets/stats${eventId != null ? `?event_id=${eventId}` : ""}`),
  importUserBets: (body: { event_name: string; combos: BetCombo[]; session_id?: number }) =>
    request<{ ok: boolean; n_imported: number; bets: UserBet[] }>("/user-bets/import", { method: "POST", body: JSON.stringify(body) }),
  updateUserBet: (id: number, patch: Partial<UserBet>) =>
    request<UserBet>(`/user-bets/${id}`, { method: "PATCH", body: JSON.stringify(patch) }),
  deleteUserBet: (id: number) =>
    request<{ ok: boolean }>(`/user-bets/${id}`, { method: "DELETE" }),
};
