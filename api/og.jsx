// 1200x630 Open Graph preview card, rendered at the edge with @vercel/og.
// /api/og            -> generic WAKE card (default site preview)
// /api/og?ship=<slug> -> per-ship card with line color and live status.
// Self-contained (no _fleet.js import) so the edge bundle stays minimal.
import { ImageResponse } from "@vercel/og";

export const config = { runtime: "edge" };

// DATA_BRANCH: flip to "main" when the feature branch is merged.
const DATA_BRANCH = "claude/cruise-ship-tracking-nsefj4";
const RAW = `https://raw.githubusercontent.com/turetskyadam-cyber/Wake-/${DATA_BRANCH}/`;

async function fetchJSON(url) {
  try { const r = await fetch(url); return r.ok ? await r.json() : null; } catch (e) { return null; }
}

export default async function handler(req) {
  let ship = null, status = null;
  try {
    const slug = (new URL(req.url).searchParams.get("ship") || "").toLowerCase().trim();
    if (slug) {
      const fleet = await fetchJSON(RAW + "fleet.json");
      ship = fleet?.ships?.find(s => s.slug === slug || s.mmsi === slug) || null;
      if (ship) {
        const snap = await fetchJSON(RAW + "positions.json");
        const fix = snap?.s?.[ship.mmsi];
        if (fix) status = fix[2] ? "IN PORT" : `${(+fix[4]).toFixed(1)} KN · UNDERWAY`;
      }
    }
  } catch (e) {}

  const accent = ship?.color || "#e2bd72";
  const title = ship ? ship.name : "WAKE";
  const sub = ship ? ship.line.toUpperCase() : "LIVE CRUISE FLEET TRACKER";

  try {
    return new ImageResponse(
      (
        <div style={{
          width: "100%", height: "100%", display: "flex", flexDirection: "column",
          justifyContent: "flex-end", padding: "64px 72px",
          background: "linear-gradient(135deg, #04101a 0%, #0a2d3f 100%)",
          fontFamily: "ui-sans-serif, system-ui",
        }}>
          <div style={{ position: "absolute", top: 0, left: 0, width: "100%", height: 10, background: accent, display: "flex" }} />
          <div style={{ display: "flex", color: "#e2bd72", fontSize: 30, letterSpacing: 10, marginBottom: 18 }}>WAKE</div>
          <div style={{ display: "flex", color: "#eaf1f3", fontSize: ship && ship.name.length > 22 ? 64 : 78, fontWeight: 700, lineHeight: 1.05 }}>{title}</div>
          <div style={{ display: "flex", alignItems: "center", gap: 22, marginTop: 24 }}>
            <div style={{ display: "flex", color: accent, fontSize: 28, letterSpacing: 5 }}>{sub}</div>
            {status ? <div style={{ display: "flex", color: "#9fb4bf", fontSize: 28, letterSpacing: 3 }}>· {status}</div> : null}
          </div>
          <div style={{ display: "flex", color: "#56707c", fontSize: 22, letterSpacing: 3, marginTop: 30 }}>
            {ship ? "LIVE POSITION · 7-DAY TRAIL · SEA CONDITIONS" : "TRACK 200+ CRUISE SHIPS IN REAL TIME"}
          </div>
        </div>
      ),
      {
        width: 1200, height: 630,
        headers: { "Cache-Control": "public, s-maxage=900, stale-while-revalidate=86400" },
      }
    );
  } catch (e) {
    return new Response("OG render failed", { status: 500 });
  }
}
