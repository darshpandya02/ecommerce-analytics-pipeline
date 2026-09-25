import { Card, DataError, PageHead } from "@/components/ui";
import { cohorts } from "@/lib/db";
import { int, pct } from "@/lib/format";

export const revalidate = 120;

// Sequential single-hue ramp (light -> dark). Ink flips to white on the darker steps.
const RAMP = ["var(--seq-100)", "var(--seq-250)", "var(--seq-400)", "var(--seq-550)", "var(--seq-700)"];

function cell(rate: number) {
  const i = Math.min(RAMP.length - 1, Math.floor(rate * RAMP.length * 0.999));
  return { background: RAMP[i], color: i >= 2 ? "#ffffff" : "#0b0b0b" };
}

export default async function CohortsPage() {
  let rows;
  try {
    rows = await cohorts();
  } catch (e) {
    return <DataError error={e} />;
  }
  const weeks = [...new Set(rows.map((r) => r.cohort_week))];
  const maxWeek = Math.max(0, ...rows.map((r) => r.week_number));
  const by = new Map(rows.map((r) => [`${r.cohort_week}:${r.week_number}`, r]));
  return (
    <div style={{ display: "grid", gap: 16, gridTemplateColumns: "minmax(0, 1fr)" }}>
      <PageHead title="Weekly cohort retention">
        Customers grouped by the week they were first seen; each cell is the share of the cohort with at least one session in
        that week. The first cohort also contains customers who existed before the data window started, so it reads higher.
      </PageHead>
      <Card title="Active share by weeks since first visit" sub="Hover a cell for counts. Darker = higher retention.">
        <div style={{ overflowX: "auto" }}>
          <table className="data" style={{ width: "auto" }}>
            <thead>
              <tr>
                <th>Cohort week</th>
                <th className="r">Customers</th>
                {Array.from({ length: maxWeek + 1 }, (_, i) => <th key={i} className="r">Week {i}</th>)}
              </tr>
            </thead>
            <tbody>
              {weeks.map((w) => {
                const size = by.get(`${w}:0`)?.cohort_size ?? rows.find((r) => r.cohort_week === w)?.cohort_size ?? 0;
                return (
                  <tr key={w}>
                    <td className="num">{w}</td>
                    <td className="r">{int(size)}</td>
                    {Array.from({ length: maxWeek + 1 }, (_, i) => {
                      const c = by.get(`${w}:${i}`);
                      if (!c) return <td key={i} />;
                      return (
                        <td key={i} className="r" title={`${int(c.active_customers)} active, ${int(c.purchasing_customers)} purchasing of ${int(c.cohort_size)}`}
                          style={{ ...cell(c.retention_rate), minWidth: 72, borderBottom: "2px solid var(--surface-1)", borderRight: "2px solid var(--surface-1)" }}>
                          {pct(c.retention_rate, 0)}
                        </td>
                      );
                    })}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
