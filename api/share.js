// Serves /s/<slug> (via the vercel.json rewrite): a tiny HTML page with
// per-ship Open Graph / Twitter meta for link previews, then an instant
// redirect to the static app at /?ship=<slug>. Crawlers read the meta;
// humans never notice the hop. Unknown slugs bounce to the homepage.
import { getShip, getStatus } from "./_fleet.js";

const SITE = "https://wake-rose.vercel.app";
const esc = s => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

export default async function handler(req, res) {
  const ship = await getShip(req.query.slug);
  if (!ship) {
    res.statusCode = 302;
    res.setHeader("Location", "/");
    res.end();
    return;
  }

  const st = await getStatus(ship.mmsi);
  const live = st
    ? (st.inPort ? "currently in port" : `underway at ${(+st.spd).toFixed(1)} kn`)
    : "live position on the map";
  const title = `Track ${ship.name} Live · WAKE`;
  const desc = `${ship.name} (${ship.line}) — ${live}. Real-time position, 7-day wake trail, itinerary and sea conditions on WAKE.`;
  const appUrl = `${SITE}/?ship=${ship.slug}`;
  const ogImg = `${SITE}/api/og?ship=${ship.slug}`;

  const html = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<title>${esc(title)}</title>
<link rel="canonical" href="${esc(appUrl)}" />
<meta property="og:type" content="website" />
<meta property="og:site_name" content="WAKE" />
<meta property="og:title" content="${esc(title)}" />
<meta property="og:description" content="${esc(desc)}" />
<meta property="og:url" content="${esc(appUrl)}" />
<meta property="og:image" content="${esc(ogImg)}" />
<meta property="og:image:width" content="1200" />
<meta property="og:image:height" content="630" />
<meta name="twitter:card" content="summary_large_image" />
<meta name="twitter:title" content="${esc(title)}" />
<meta name="twitter:description" content="${esc(desc)}" />
<meta name="twitter:image" content="${esc(ogImg)}" />
<meta http-equiv="refresh" content="0;url=${esc(appUrl)}" />
<script>location.replace(${JSON.stringify(appUrl)});</script>
</head>
<body style="background:#04101a;color:#eaf1f3;font-family:system-ui">
<p style="padding:24px">Taking you to <a href="${esc(appUrl)}" style="color:#e2bd72">${esc(ship.name)} on WAKE</a>…</p>
</body>
</html>`;

  res.setHeader("Content-Type", "text/html; charset=utf-8");
  res.setHeader("Cache-Control", "public, s-maxage=600, stale-while-revalidate=86400");
  res.end(html);
}
