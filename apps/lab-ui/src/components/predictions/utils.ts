/** American odds → decimal odds. */
export function americanToDecimal(american: number | null | undefined): number | null {
  if (american == null) return null;
  return american > 0 ? american / 100 + 1 : 100 / Math.abs(american) + 1;
}

/** Format American odds for display (e.g. "+150", "-200", decimal "2.50"). */
export function fmtOdds(american: number | null | undefined): string {
  if (american == null) return "—";
  const dec = americanToDecimal(american);
  const sign = american > 0 ? "+" : "";
  return `${sign}${american} · ${dec!.toFixed(2)}`;
}

/** Last name (for compact model chips / labels). */
export function lastName(name: string): string {
  const parts = name.trim().split(/\s+/);
  return parts[parts.length - 1] || name;
}

/** Initials for the avatar fallback. */
export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

/** Stable color per model short, for chip accents. */
export function modelColor(short: string): string {
  let h = 0;
  for (let i = 0; i < short.length; i++) h = (h * 31 + short.charCodeAt(i)) % 360;
  return `hsl(${h}, 65%, 60%)`;
}

/** Photo URL for a fighter name (lab-api serves by-name). */
export function photoUrl(name: string): string {
  return `/api/fighters/by-name/${encodeURIComponent(name)}/photo`;
}
