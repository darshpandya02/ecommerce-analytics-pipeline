"use client";

import { useEffect, useRef, useState } from "react";
import { int, pct, usd } from "@/lib/format";

// Server components cannot pass functions to client components, so formats are named.
export type Fmt = "usd" | "int" | "pct1" | "pct2";
const FORMATS: Record<Fmt, (n: number) => string> = { usd, int, pct1: (n) => pct(n, 1), pct2: (n) => pct(n, 2) };

function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [w, setW] = useState(720);
  useEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver(([e]) => setW(Math.max(280, Math.floor(e.contentRect.width))));
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);
  return [ref, w] as const;
}

// Axis max = 4 clean steps, so every tick lands on a round number.
function niceMax(v: number) {
  if (v <= 0) return 1;
  const raw = v / 4;
  const p = Math.pow(10, Math.floor(Math.log10(raw)));
  const n = raw / p;
  const step = n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10;
  return step * p * 4;
}

const M = { top: 12, right: 16, bottom: 26, left: 56 };

function shortDay(d: string) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(d)) return d;
  const [, m, day] = d.split("-");
  return `${Number(m)}/${Number(day)}`;
}

function Axis({ w, h, max, fmt }: { w: number; h: number; max: number; fmt: (n: number) => string }) {
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => f * max);
  const ih = h - M.top - M.bottom;
  return (
    <g>
      {ticks.map((t) => {
        const y = M.top + ih - (t / max) * ih;
        return (
          <g key={t}>
            <line x1={M.left} x2={w - M.right} y1={y} y2={y} stroke={t === 0 ? "var(--axis)" : "var(--grid)"} strokeWidth={1} />
            <text x={M.left - 8} y={y + 4} textAnchor="end" fontSize={11} fill="var(--text-muted)" className="num">
              {fmt(t)}
            </text>
          </g>
        );
      })}
    </g>
  );
}

function XLabels({ xs, pos, h }: { xs: string[]; pos: (i: number) => number; h: number }) {
  const every = Math.max(1, Math.ceil(xs.length / 8));
  return (
    <g>
      {xs.map((x, i) =>
        i % every === 0 || i === xs.length - 1 ? (
          <text key={x} x={pos(i)} y={h - 8} textAnchor="middle" fontSize={11} fill="var(--text-muted)" className="num">
            {shortDay(x)}
          </text>
        ) : null,
      )}
    </g>
  );
}

export type Series = { key: string; label: string; color: string };

export function LineChart({
  data,
  series,
  format,
  height = 240,
}: {
  data: { x: string; [k: string]: number | string }[];
  series: Series[];
  format: Fmt;
  height?: number;
}) {
  const fmt = FORMATS[format];
  const [ref, w] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const max = niceMax(Math.max(1, ...data.flatMap((d) => series.map((s) => Number(d[s.key]) || 0))));
  const iw = w - M.left - M.right;
  const ih = height - M.top - M.bottom;
  const x = (i: number) => M.left + (data.length <= 1 ? iw / 2 : (i / (data.length - 1)) * iw);
  const y = (v: number) => M.top + ih - (v / max) * ih;
  const last = data.length - 1;
  return (
    <div ref={ref} style={{ position: "relative" }}>
      {series.length > 1 && (
        <div style={{ display: "flex", gap: 16, fontSize: 12, marginBottom: 6 }} className="secondary">
          {series.map((s) => (
            <span key={s.key} style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
              <span style={{ width: 14, height: 2, background: s.color, display: "inline-block", borderRadius: 1 }} />
              {s.label}
            </span>
          ))}
        </div>
      )}
      <svg
        width={w}
        height={height}
        role="img"
        onPointerMove={(e) => {
          const r = (e.currentTarget as SVGSVGElement).getBoundingClientRect();
          const px = e.clientX - r.left;
          const i = Math.round(((px - M.left) / iw) * last);
          setHover(Math.min(last, Math.max(0, i)));
        }}
        onPointerLeave={() => setHover(null)}
      >
        <Axis w={w} h={height} max={max} fmt={fmt} />
        {series.map((s, si) => (
          <g key={s.key}>
            {si === 0 && (
              <path
                d={`M${x(0)},${y(0)} ` + data.map((d, i) => `L${x(i)},${y(Number(d[s.key]) || 0)}`).join(" ") + ` L${x(last)},${y(0)} Z`}
                fill="var(--series-1-wash)"
              />
            )}
            <path
              d={data.map((d, i) => `${i ? "L" : "M"}${x(i)},${y(Number(d[s.key]) || 0)}`).join(" ")}
              fill="none"
              stroke={s.color}
              strokeWidth={2}
              strokeLinejoin="round"
              strokeLinecap="round"
            />
            {last >= 0 && <circle cx={x(last)} cy={y(Number(data[last][s.key]) || 0)} r={4} fill={s.color} stroke="var(--surface-1)" strokeWidth={2} />}
          </g>
        ))}
        <XLabels xs={data.map((d) => d.x)} pos={x} h={height} />
        {hover !== null && (
          <g>
            <line x1={x(hover)} x2={x(hover)} y1={M.top} y2={M.top + ih} stroke="var(--axis)" strokeWidth={1} />
            {series.map((s) => (
              <circle key={s.key} cx={x(hover)} cy={y(Number(data[hover][s.key]) || 0)} r={4} fill={s.color} stroke="var(--surface-1)" strokeWidth={2} />
            ))}
          </g>
        )}
      </svg>
      {hover !== null && (
        <div className="tooltip" style={{ left: Math.min(x(hover) + 12, w - 170), top: 24 }}>
          <div className="muted" style={{ marginBottom: 4 }}>{data[hover].x}</div>
          {series.map((s) => (
            <div key={s.key} style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ width: 10, height: 2, background: s.color, display: "inline-block" }} />
              <strong className="num">{fmt(Number(data[hover][s.key]) || 0)}</strong>
              <span className="secondary">{s.label}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function ColumnChart({
  data,
  format,
  label,
  height = 200,
  color = "var(--series-1)",
  details,
}: {
  data: { x: string; y: number }[];
  format: Fmt;
  label: string;
  height?: number;
  color?: string;
  details?: string[];
}) {
  const fmt = FORMATS[format];
  const [ref, w] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const max = niceMax(Math.max(1, ...data.map((d) => d.y)));
  const iw = w - M.left - M.right;
  const ih = height - M.top - M.bottom;
  const band = iw / Math.max(1, data.length);
  const bw = Math.min(24, Math.max(2, band - 2));
  const cx = (i: number) => M.left + band * i + band / 2;
  return (
    <div ref={ref} style={{ position: "relative" }}>
      <svg width={w} height={height} role="img" aria-label={label} onPointerLeave={() => setHover(null)}>
        <Axis w={w} h={height} max={max} fmt={fmt} />
        {data.map((d, i) => {
          const bh = (d.y / max) * ih;
          const x0 = cx(i) - bw / 2;
          const y0 = M.top + ih - bh;
          const r = Math.min(4, bw / 2, bh);
          return (
            <g key={d.x + i} onPointerEnter={() => setHover(i)}>
              <rect x={cx(i) - band / 2} y={M.top} width={band} height={ih} fill="transparent" />
              {bh > 0 && (
                <path
                  d={`M${x0},${M.top + ih} L${x0},${y0 + r} Q${x0},${y0} ${x0 + r},${y0} L${x0 + bw - r},${y0} Q${x0 + bw},${y0} ${x0 + bw},${y0 + r} L${x0 + bw},${M.top + ih} Z`}
                  fill={color}
                  opacity={hover === null || hover === i ? 1 : 0.55}
                />
              )}
            </g>
          );
        })}
        <XLabels xs={data.map((d) => d.x)} pos={cx} h={height} />
      </svg>
      {hover !== null && (
        <div className="tooltip" style={{ left: Math.min(cx(hover) + 12, w - 200), top: 8 }}>
          <div className="muted" style={{ marginBottom: 2 }}>{data[hover].x}</div>
          <strong className="num">{fmt(data[hover].y)}</strong> <span className="secondary">{label}</span>
          {details && <div className="secondary" style={{ marginTop: 4 }}>{details[hover]}</div>}
        </div>
      )}
    </div>
  );
}

export function HBars({
  rows,
  format,
  notes,
}: {
  rows: { label: string; value: number }[];
  format: Fmt;
  notes?: string[];
}) {
  const fmt = FORMATS[format];
  const max = Math.max(1, ...rows.map((r) => r.value));
  const [hover, setHover] = useState<number | null>(null);
  return (
    <div style={{ display: "grid", gap: 10 }}>
      {rows.map((r, i) => (
        <div
          key={r.label}
          onPointerEnter={() => setHover(i)}
          onPointerLeave={() => setHover(null)}
          style={{ display: "grid", gridTemplateColumns: "140px 1fr", alignItems: "center", gap: 12 }}
        >
          <span className="secondary" style={{ fontSize: 13 }}>{r.label}</span>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <div
              style={{
                height: 20,
                width: `${Math.max(0.5, (r.value / max) * 78)}%`,
                background: "var(--series-1)",
                borderRadius: "0 4px 4px 0",
                opacity: hover === null || hover === i ? 1 : 0.6,
              }}
            />
            <span className="num" style={{ fontSize: 13 }}>
              <strong>{fmt(r.value)}</strong>
              {notes?.[i] && <span className="muted"> {notes[i]}</span>}
            </span>
          </div>
        </div>
      ))}
    </div>
  );
}
