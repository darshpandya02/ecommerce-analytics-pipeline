import type { ReactNode } from "react";

export function Tile({ label, value, delta, sub }: { label: string; value: ReactNode; delta?: { text: string; good: boolean | null }; sub?: ReactNode }) {
  return (
    <div className="card" style={{ minWidth: 0 }}>
      <div className="secondary" style={{ fontSize: 13 }}>{label}</div>
      <div style={{ fontSize: 26, fontWeight: 600, marginTop: 4 }}>{value}</div>
      {delta && (
        <div style={{ fontSize: 12, marginTop: 2, color: delta.good === null ? "var(--text-muted)" : delta.good ? "var(--delta-good)" : "var(--critical)" }}>
          {delta.text}
        </div>
      )}
      {sub && <div className="muted" style={{ fontSize: 12, marginTop: 2 }}>{sub}</div>}
    </div>
  );
}

export function Card({ title, sub, children }: { title: string; sub?: ReactNode; children: ReactNode }) {
  return (
    <section className="card">
      <h2 style={{ fontSize: 15, fontWeight: 600 }}>{title}</h2>
      {sub && <p className="muted" style={{ fontSize: 12, marginTop: 2, marginBottom: 10 }}>{sub}</p>}
      <div style={{ marginTop: sub ? 0 : 10 }}>{children}</div>
    </section>
  );
}

const STATUS: Record<string, { color: string; icon: string; label: string }> = {
  success: { color: "var(--good)", icon: "✓", label: "Success" },
  warning: { color: "var(--warning)", icon: "!", label: "Warning" },
  failed: { color: "var(--critical)", icon: "✕", label: "Failed" },
  running: { color: "var(--text-muted)", icon: "…", label: "Running" },
  pass: { color: "var(--good)", icon: "✓", label: "Pass" },
  fail: { color: "var(--critical)", icon: "✕", label: "Fail" },
  caught: { color: "var(--good)", icon: "✓", label: "Caught" },
  missed: { color: "var(--critical)", icon: "✕", label: "Missed" },
};

export function Status({ s }: { s: string }) {
  const v = STATUS[s] ?? STATUS.running;
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 6, whiteSpace: "nowrap" }}>
      <span
        aria-hidden
        style={{ width: 16, height: 16, borderRadius: 8, background: v.color, color: "#fff", fontSize: 10, fontWeight: 700, display: "inline-flex", alignItems: "center", justifyContent: "center" }}
      >
        {v.icon}
      </span>
      {v.label}
    </span>
  );
}

export function PageHead({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div style={{ marginBottom: 16 }}>
      <h1 style={{ fontSize: 22, fontWeight: 600 }}>{title}</h1>
      {children && <p className="secondary" style={{ fontSize: 14, marginTop: 4, maxWidth: 820 }}>{children}</p>}
    </div>
  );
}

export function DataError({ error }: { error: unknown }) {
  return (
    <div className="card" role="alert">
      <strong>Warehouse unavailable.</strong>{" "}
      <span className="secondary">{error instanceof Error ? error.message : String(error)}</span>
    </div>
  );
}
