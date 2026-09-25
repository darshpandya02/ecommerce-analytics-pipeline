"use client";
import { useEffect, useState } from "react";

// Minutes since the last committed load, recomputed in the browser so a cached page still
// shows current staleness.
export function Freshness({ at }: { at: string | null }) {
  const [now, setNow] = useState<number | null>(null);
  useEffect(() => {
    const tick = () => setNow(Date.now());
    const first = setTimeout(tick, 0);
    const t = setInterval(tick, 15000);
    return () => {
      clearTimeout(first);
      clearInterval(t);
    };
  }, []);
  if (!at) return <>n/a</>;
  const mins = ((now ?? new Date(at).getTime()) - new Date(at).getTime()) / 60000;
  return <span suppressHydrationWarning>{now === null ? "..." : `${Math.max(0, mins).toFixed(0)} min`}</span>;
}
