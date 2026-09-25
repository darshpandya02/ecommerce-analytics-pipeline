import { ColumnChart, LineChart } from "@/components/charts";
import { Card, DataError, PageHead, Tile } from "@/components/ui";
import { dailyConversion, dailyRevenue } from "@/lib/db";
import { int, pct, usd, usd2 } from "@/lib/format";

export const revalidate = 120;

function sum<T>(rows: T[], f: (r: T) => number) {
  return rows.reduce((a, r) => a + f(r), 0);
}

function delta(cur: number, prev: number, upIsGood = true) {
  if (!prev) return undefined;
  const d = (cur - prev) / prev;
  return { text: `${d >= 0 ? "+" : ""}${pct(d)} vs prior 7 days`, good: d === 0 ? null : (d > 0) === upIsGood };
}

export default async function RevenuePage() {
  let rev, conv;
  try {
    [rev, conv] = await Promise.all([dailyRevenue(), dailyConversion()]);
  } catch (e) {
    return <DataError error={e} />;
  }
  const last7 = rev.slice(-7);
  const prev7 = rev.slice(-14, -7);
  const conv7 = conv.slice(-7);
  const conv7p = conv.slice(-14, -7);
  const g = sum(last7, (r) => r.gross_revenue);
  const gp = sum(prev7, (r) => r.gross_revenue);
  const o = sum(last7, (r) => r.orders);
  const op = sum(prev7, (r) => r.orders);
  const cr = sum(conv7, (r) => r.order_sessions) / Math.max(1, sum(conv7, (r) => r.sessions));
  const crp = sum(conv7p, (r) => r.order_sessions) / Math.max(1, sum(conv7p, (r) => r.sessions));
  const refunded = sum(last7, (r) => r.refunded_amount);
  const refundedP = sum(prev7, (r) => r.refunded_amount);

  return (
    <div style={{ display: "grid", gap: 16, gridTemplateColumns: "minmax(0, 1fr)" }}>
      <PageHead title="Revenue and orders">
        Daily figures from <code>ecom_marts.mart_daily_revenue</code> (America/New_York days). The current day is partial.
        Refunds are counted on the day they were issued.
      </PageHead>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(190px, 1fr))", gap: 12 }}>
        <Tile label="Gross revenue, last 7 days" value={usd(g)} delta={delta(g, gp)} />
        <Tile label="Orders, last 7 days" value={int(o)} delta={delta(o, op)} />
        <Tile label="Average order value" value={usd2(g / Math.max(1, o))} delta={delta(g / Math.max(1, o), gp / Math.max(1, op))} />
        <Tile label="Session conversion" value={pct(cr, 2)} delta={delta(cr, crp)} />
        <Tile label="Refunded, last 7 days" value={usd(refunded)} delta={delta(refunded, refundedP, false)} />
      </div>
      <Card title="Daily revenue" sub="Gross order value and net of refunds issued that day">
        <LineChart
          data={rev.map((r) => ({ x: r.day, gross: r.gross_revenue, net: r.net_revenue }))}
          series={[
            { key: "gross", label: "Gross revenue", color: "var(--series-1)" },
            { key: "net", label: "Net of refunds", color: "var(--series-2)" },
          ]}
          format="usd"
        />
      </Card>
      <Card title="Orders per day">
        <ColumnChart
          data={rev.map((r) => ({ x: r.day, y: r.orders }))}
          format="int"
          label="orders"
          details={rev.map((r) => `${int(r.first_orders)} first-time, AOV ${r.avg_order_value ? usd2(r.avg_order_value) : "n/a"}`)}
        />
      </Card>
      <details className="card">
        <summary style={{ cursor: "pointer", fontSize: 14 }}>Table view</summary>
        <table className="data" style={{ marginTop: 10 }}>
          <thead><tr><th>Day</th><th className="r">Orders</th><th className="r">Gross</th><th className="r">Refunded</th><th className="r">Net</th><th className="r">AOV</th><th className="r">First orders</th></tr></thead>
          <tbody>
            {[...rev].reverse().map((r) => (
              <tr key={r.day}>
                <td className="num">{r.day}</td><td className="r">{int(r.orders)}</td><td className="r">{usd2(r.gross_revenue)}</td>
                <td className="r">{usd2(r.refunded_amount)}</td><td className="r">{usd2(r.net_revenue)}</td>
                <td className="r">{r.avg_order_value ? usd2(r.avg_order_value) : "n/a"}</td><td className="r">{int(r.first_orders)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </div>
  );
}
