import { ColumnChart } from "@/components/charts";
import { Freshness } from "@/components/freshness";
import { Card, DataError, PageHead, Status, Tile } from "@/components/ui";
import { anomalies, checkStats, falsePositives, healthSummary, runs } from "@/lib/db";
import { dur, int, ts } from "@/lib/format";

export const revalidate = 60;

const REPO = "https://github.com/darshpandya02/ecommerce-analytics-pipeline";

function short(o: unknown) {
  if (!o) return "";
  const s = JSON.stringify(o);
  return s.length > 140 ? s.slice(0, 137) + "..." : s;
}

export default async function HealthPage() {
  let h, rs, cs, an, fp;
  try {
    [h, rs, cs, an, fp] = await Promise.all([healthSummary(), runs(60), checkStats(500), anomalies(), falsePositives()]);
  } catch (e) {
    return <DataError error={e} />;
  }
  const last = rs[0];
  const chrono = [...rs].reverse().filter((r) => r.duration_s != null);
  const scored = an.filter((a) => a.detected !== null);
  const caught = scored.filter((a) => a.detected).length;
  const mb = (h.ecom_bytes ?? 0) / 1e6;
  return (
    <div style={{ display: "grid", gap: 16, gridTemplateColumns: "minmax(0, 1fr)" }}>
      <PageHead title="Pipeline health">
        Every run of the GitHub Actions schedule records itself in <code>ecom_ops.pipeline_runs</code>; check outcomes land in{" "}
        <code>ecom_ops.quality_results</code>. Durations and latency percentiles below cover runs by the scheduler (cron and
        manual dispatch), not local development runs.
      </PageHead>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(190px, 1fr))", gap: 12 }}>
        <Tile label="Data freshness" value={<Freshness at={h.last_loaded_at} />} sub={`last load committed ${ts(h.last_loaded_at)} ET`} />
        <Tile label="Last run" value={last ? <Status s={last.status} /> : "n/a"} sub={last ? `#${last.run_id}, ${ts(last.started_at)} ET` : undefined} />
        <Tile label="Runs, last 24 h" value={`${h.ok_24h} / ${h.runs_24h}`} sub="completed without failure" />
        <Tile label="Run duration p50 / p95" value={`${dur(h.p50_duration_s)} / ${dur(h.p95_duration_s)}`} sub={`${int(h.scheduled_runs)} scheduler runs`} />
        <Tile label="Event to mart latency" value={`${dur(h.p50_latency_s)}`} sub={`median of per-run p50; p95 ${dur(h.p95_latency_s)}`} />
        <Tile label="Warehouse size" value={`${mb.toFixed(1)} MB`} sub="ecom_* schemas, budget 150 MB" />
        <Tile label="Injected anomalies caught" value={scored.length ? `${caught} / ${scored.length}` : "none yet"} sub={`clean runs with a failed check: ${fp.clean_runs_with_failures} / ${fp.clean_runs}`} />
      </div>
      <Card title="Run duration" sub="Pipeline process time per run (bootstrap through retention), oldest to newest">
        <ColumnChart data={chrono.map((r) => ({ x: `#${r.run_id}`, y: r.duration_s ?? 0 }))} format="int" label="seconds"
          details={chrono.map((r) => `${r.status}, ${int(r.rows_inserted ?? 0)} rows inserted, ${ts(r.started_at)} ET`)} />
      </Card>
      <Card title="Event to mart latency per run" sub="Median seconds from an order's event time to its row being published in fct_orders, for orders loaded in that run">
        <ColumnChart data={chrono.filter((r) => r.latency_p50_s != null).map((r) => ({ x: `#${r.run_id}`, y: r.latency_p50_s ?? 0 }))} format="int" label="seconds (p50)"
          details={chrono.filter((r) => r.latency_p50_s != null).map((r) => `p95 ${dur(r.latency_p95_s)}, ${int(r.orders_published ?? 0)} orders`)} />
      </Card>
      <Card title="Run history" sub="Most recent 60 runs">
        <div style={{ overflowX: "auto" }}>
          <table className="data">
            <thead>
              <tr><th>Run</th><th>Trigger</th><th>Started (ET)</th><th>Status</th><th className="r">Emitted</th><th className="r">Inserted</th><th className="r">Dup. dropped</th><th className="r">Duration</th><th className="r">Latency p50</th><th>Failed checks</th></tr>
            </thead>
            <tbody>
              {rs.map((r) => (
                <tr key={r.run_id}>
                  <td className="num">{r.github_run_id ? <a href={`${REPO}/actions/runs/${r.github_run_id}`} style={{ textDecoration: "underline" }}>#{r.run_id}</a> : `#${r.run_id}`}</td>
                  <td>{r.trigger}</td>
                  <td className="num">{ts(r.started_at)}</td>
                  <td><Status s={r.status} /></td>
                  <td className="r">{r.rows_emitted == null ? "" : int(r.rows_emitted)}</td>
                  <td className="r">{r.rows_inserted == null ? "" : int(r.rows_inserted)}</td>
                  <td className="r">{r.duplicates_dropped == null ? "" : int(r.duplicates_dropped)}</td>
                  <td className="r">{dur(r.duration_s)}</td>
                  <td className="r">{dur(r.latency_p50_s)}</td>
                  <td style={{ fontSize: 12 }}>{r.error ? <span>{r.error.slice(0, 120)}</span> : (r.failed_checks ?? []).join(", ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
      <Card title="Injected anomalies" sub="Ground truth written by the source when it corrupts a batch; caught means a check designed for that failure mode failed in the same run">
        <table className="data">
          <thead><tr><th>Run</th><th>Anomaly</th><th>Trigger</th><th className="r">Rows affected</th><th>Result</th><th>Flagged by</th></tr></thead>
          <tbody>
            {an.map((a) => (
              <tr key={`${a.run_id}-${a.anomaly_type}`}>
                <td className="num">#{a.run_id}</td><td>{a.anomaly_type}</td><td>{a.trigger}</td><td className="r">{int(a.rows_affected)}</td>
                <td>{a.detected === null ? "n/a" : <Status s={a.detected ? "caught" : "missed"} />}</td>
                <td style={{ fontSize: 12 }}>{(a.detected_by ?? []).join(", ")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
      <Card title="Quality checks" sub="Great Expectations suites (raw batch, marts, reconciliation), dbt tests and dbt source freshness, across recorded runs">
        <div style={{ overflowX: "auto" }}>
          <table className="data">
            <thead><tr><th>Check</th><th>Suite</th><th>Severity</th><th className="r">Runs</th><th className="r">Failures</th><th>Last failure</th><th>Last failing observation</th></tr></thead>
            <tbody>
              {cs.map((c) => (
                <tr key={c.check_name}>
                  <td style={{ fontSize: 12, wordBreak: "break-word", maxWidth: 380 }}>{c.check_name}</td><td>{c.suite}</td><td>{c.severity}</td>
                  <td className="r">{int(c.runs)}</td>
                  <td className="r">{c.failures ? <Status s="fail" /> : null} {int(c.failures)}</td>
                  <td className="num">{c.last_failed_run ? `#${c.last_failed_run}` : ""}</td>
                  <td className="muted" style={{ fontSize: 11, maxWidth: 360, wordBreak: "break-all" }}>{short(c.last_observed)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
