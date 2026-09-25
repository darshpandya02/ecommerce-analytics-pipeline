export const usd = (n: number) =>
  Math.abs(n) >= 10000
    ? `$${(n / 1000).toFixed(Math.abs(n) >= 100000 ? 0 : 1)}K`
    : `$${n.toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
export const usd2 = (n: number) => `$${n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
export const int = (n: number) => Math.round(n).toLocaleString("en-US");
export const pct = (n: number, d = 1) => `${(n * 100).toFixed(d)}%`;
export function dur(s: number | null | undefined) {
  if (s == null || Number.isNaN(s)) return "n/a";
  if (s < 90) return `${s.toFixed(1)} s`;
  if (s < 5400) return `${(s / 60).toFixed(1)} min`;
  return `${(s / 3600).toFixed(1)} h`;
}
export function ts(s: string | null | undefined) {
  if (!s) return "n/a";
  return new Date(s).toLocaleString("en-US", {
    timeZone: "America/New_York", month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
  });
}
