const MODEL_COLORS: Record<string, string> = {
  XGB: "#8b5cf6",   // violeta
  RF: "#3b82f6",    // azul
  CB: "#0ea5e9",    // azul claro
  Deep: "#ec4899",  // rosa
};

export const DASHBOARD_MODEL_ORDER = ["XGB", "RF", "CB", "Deep"] as const;

export function modelColor(short: string): string {
  return MODEL_COLORS[short] ?? "#a1a1aa";
}
