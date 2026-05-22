export function fmtPct(v: number | null | undefined, decimals = 1): string {
  if (v == null) return "—";
  return `${(v * 100).toFixed(decimals)}%`;
}

export function fmtDate(s: string | null | undefined): string {
  if (!s) return "—";
  try {
    return new Intl.DateTimeFormat("es-ES", {
      day: "numeric",
      month: "short",
      year: "numeric",
    }).format(new Date(s));
  } catch {
    return s;
  }
}
