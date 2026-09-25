import { HBars } from "@/components/charts";
import { Card, DataError, PageHead } from "@/components/ui";
import { refundByCategory, topProducts } from "@/lib/db";
import { int, usd2 } from "@/lib/format";

export const revalidate = 120;

export default async function ProductsPage() {
  let top, refunds;
  try {
    [top, refunds] = await Promise.all([topProducts(15), refundByCategory()]);
  } catch (e) {
    return <DataError error={e} />;
  }
  return (
    <div style={{ display: "grid", gap: 16, gridTemplateColumns: "minmax(0, 1fr)" }}>
      <PageHead title="Top products and refunds">
        Line-item revenue from <code>ecom_marts.mart_top_products</code> over the orders in the warehouse, and refund rates
        from <code>ecom_marts.mart_refund_rate</code>.
      </PageHead>
      <Card title="Top 15 products by revenue">
        <HBars rows={top.map((p) => ({ label: p.product_name, value: p.revenue }))} format="usd" notes={top.map((p) => `${int(p.units)} units`)} />
      </Card>
      <Card title="Product detail">
        <table className="data">
          <thead><tr><th>#</th><th>Product</th><th>Category</th><th className="r">Price</th><th className="r">Units</th><th className="r">Orders</th><th className="r">Revenue</th><th className="r">Revenue, 7 days</th></tr></thead>
          <tbody>
            {top.map((p) => (
              <tr key={p.product_id}>
                <td className="num">{p.revenue_rank}</td><td>{p.product_name} <span className="muted">{p.product_id}</span></td><td>{p.category}</td>
                <td className="r">{usd2(p.price)}</td><td className="r">{int(p.units)}</td><td className="r">{int(p.orders)}</td>
                <td className="r">{usd2(p.revenue)}</td><td className="r">{usd2(p.revenue_7d)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
      <Card title="Refund rate by category" sub="Share of orders containing the category that were later refunded">
        <HBars rows={refunds.map((r) => ({ label: r.category, value: r.refund_rate ?? 0 }))} format="pct1" notes={refunds.map((r) => `${int(r.refunded_orders)} of ${int(r.orders)} orders`)} />
      </Card>
    </div>
  );
}
