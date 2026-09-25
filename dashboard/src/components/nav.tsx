"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  ["/", "Revenue"],
  ["/funnel", "Funnel"],
  ["/cohorts", "Cohorts"],
  ["/products", "Products"],
  ["/health", "Pipeline health"],
] as const;

export function Nav() {
  const path = usePathname();
  return (
    <nav style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
      {LINKS.map(([href, label]) => (
        <Link key={href} href={href} className="nav" aria-current={path === href ? "page" : undefined}>
          {label}
        </Link>
      ))}
    </nav>
  );
}
