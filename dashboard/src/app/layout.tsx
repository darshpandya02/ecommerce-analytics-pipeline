import type { Metadata } from "next";
import { Nav } from "@/components/nav";
import "./globals.css";

export const metadata: Metadata = {
  title: "E-commerce analytics pipeline",
  description:
    "Read-only dashboard over a scheduled batch pipeline: synthetic store events, Parquet raw zone, Postgres, dbt marts and Great Expectations checks.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en">
      <body>
        <header style={{ borderBottom: "1px solid var(--border)", background: "var(--surface-1)" }}>
          <div style={{ maxWidth: 1180, margin: "0 auto", padding: "12px 20px", display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16, flexWrap: "wrap" }}>
            <div>
              <div style={{ fontWeight: 600 }}>E-commerce analytics pipeline</div>
              <div className="muted" style={{ fontSize: 12 }}>
                Synthetic store data, refreshed every 30 minutes by a scheduled pipeline.{" "}
                <a href="https://github.com/darshpandya02/ecommerce-analytics-pipeline" style={{ textDecoration: "underline" }}>Source</a>
              </div>
            </div>
            <Nav />
          </div>
        </header>
        <main style={{ maxWidth: 1180, margin: "0 auto", padding: "20px" }}>{children}</main>
      </body>
    </html>
  );
}
