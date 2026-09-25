import { HBars, LineChart } from "@/components/charts";
import { Card, DataError, PageHead } from "@/components/ui";
import { dailyConversion, funnel } from "@/lib/db";
import { int, pct } from "@/lib/format";

export const revalidate = 120;

const STAGES = [
  ["sessions", "Sessions"],
  ["product_view_sessions", "Viewed a product"],
  ["cart_sessions", "Added to cart"],
  ["checkout_sessions", "Started checkout"],
  ["order_sessions", "Placed an order"],
] as const;

export default async function FunnelPage() {
  let rows, daily;
  try {
    [rows, daily] = await Promise.all([funnel(30), dailyConversion()]);
  } catch (e) {
    return <DataError error={e} />;
  }
  const total = Object.fromEntries(STAGES.map(([k]) => [k, rows.reduce((a, r) => a + r[k], 0)])) as Record<(typeof STAGES)[number][0], number>;
  const bars = STAGES.map(([k, label]) => ({ label, value: total[k] }));
  return (
    <div style={{ display: "grid", gap: 16, gridTemplateColumns: "minmax(0, 1fr)" }}>
      <PageHead title="Conversion funnel">
        Sessions reaching each stage over the last 30 days, from <code>ecom_marts.mart_conversion_funnel</code>. A session
        counts once per stage; late events update the session they belong to (incremental merge on session_id).
      </PageHead>
      <Card title="Last 30 days" sub="Share shown is relative to the previous stage">
        <HBars rows={bars} format="int" notes={bars.map((b, i) => (i === 0 ? "" : `${pct(b.value / Math.max(1, bars[i - 1].value))} of previous`))} />
      </Card>
      <Card title="Daily session conversion rate" sub="Sessions with an order / all sessions">
        <LineChart data={daily.map((d) => ({ x: d.day, rate: d.order_sessions / Math.max(1, d.sessions) }))} series={[{ key: "rate", label: "Conversion", color: "var(--series-1)" }]} format="pct1" height={200} />
      </Card>
      <Card title="By device, last 30 days">
        <table className="data">
          <thead><tr><th>Device</th>{STAGES.map(([k, l]) => <th key={k} className="r">{l}</th>)}<th className="r">Conversion</th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.device}>
                <td>{r.device}</td>
                {STAGES.map(([k]) => <td key={k} className="r">{int(r[k])}</td>)}
                <td className="r">{pct(r.order_sessions / Math.max(1, r.sessions), 2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
