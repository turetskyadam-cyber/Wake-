// 1200x630 Open Graph preview card, rendered at the edge with @vercel/og.
// /api/og             -> generic WAKE card (default site preview)
// /api/og?ship=<slug> -> per-ship card with line color and live status.
// Plain JS with satori element objects (no JSX) so no transpile step is needed.
import { ImageResponse } from "@vercel/og";

export const config = { runtime: "edge" };

const DATA_BRANCH = "main";
const RAW = `https://raw.githubusercontent.com/turetskyadam-cyber/Wake-/${DATA_BRANCH}/`;

async function fetchJSON(url) {
  try { const r = await fetch(url); return r.ok ? await r.json() : null; } catch (e) { return null; }
}

// satori element helper: h(type, style, ...children)
const h = (type, style, ...children) => ({ type, props: { style, children: children.length === 1 ? children[0] : children } });

export default async function handler(req) {
  let ship = null, status = null;
  try {
    const slug = (new URL(req.url).searchParams.get("ship") || "").toLowerCase().trim();
    if (slug) {
      const fleet = await fetchJSON(RAW + "fleet.json");
      ship = (fleet && fleet.ships || []).find(s => s.slug === slug || s.mmsi === slug) || null;
      if (ship) {
        const snap = await fetchJSON(RAW + "positions.json");
        const fix = snap && snap.s && snap.s[ship.mmsi];
        if (fix) status = fix[2] ? "IN PORT" : `${(+fix[4]).toFixed(1)} KN · UNDERWAY`;
      }
    }
  } catch (e) {}

  const accent = (ship && ship.color) || "#e2bd72";
  const title = ship ? ship.name : "WAKE";
  const sub = ship ? ship.line.toUpperCase() : "LIVE CRUISE FLEET TRACKER";

  try {
    const card = h("div", {
      width: "100%", height: "100%", display: "flex", flexDirection: "column",
      justifyContent: "flex-end", padding: "64px 72px", position: "relative",
      background: "linear-gradient(135deg, #04101a 0%, #0a2d3f 100%)",
      fontFamily: "ui-sans-serif, system-ui",
    },
      h("div", { position: "absolute", top: 0, left: 0, width: "1200px", height: "10px", background: accent, display: "flex" }),
      h("div", { display: "flex", color: "#e2bd72", fontSize: "30px", letterSpacing: "10px", marginBottom: "18px" }, "WAKE"),
      h("div", { display: "flex", color: "#eaf1f3", fontSize: ship && ship.name.length > 22 ? "64px" : "78px", fontWeight: 700, lineHeight: 1.05 }, title),
      h("div", { display: "flex", alignItems: "center", marginTop: "24px" },
        h("div", { display: "flex", color: accent, fontSize: "28px", letterSpacing: "5px" }, sub),
        status ? h("div", { display: "flex", color: "#9fb4bf", fontSize: "28px", letterSpacing: "3px", marginLeft: "22px" }, "· " + status) : h("div", { display: "flex" })
      ),
      h("div", { display: "flex", color: "#56707c", fontSize: "22px", letterSpacing: "3px", marginTop: "30px" },
        ship ? "LIVE POSITION · 7-DAY TRAIL · SEA CONDITIONS" : "TRACK 200+ CRUISE SHIPS IN REAL TIME")
    );
    return new ImageResponse(card, {
      width: 1200, height: 630,
      headers: { "Cache-Control": "public, s-maxage=900, stale-while-revalidate=86400" },
    });
  } catch (e) {
    return new Response("OG render failed", { status: 500 });
  }
}
