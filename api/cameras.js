// Fetches live camera data from the Google Sheet and returns JSON.
// Server-side fetch avoids CORS; Vercel Edge cache keeps it fast.
//
// Sheet column headers (case-insensitive, flexible names accepted):
//   port       | name
//   flag       (emoji)
//   country
//   camview    | cam_view | description | view
//   ytid       | yt_id   | youtube_id
//   plat       | lat     | latitude
//   plon       | plon    | lon | lng   | longitude

const SHEET_ID = "10F_8H8bPROFrSsVmhJ8oZ5yJS9IftpvKpViyMEIdVMk";

// gviz endpoint works for sheets shared "Anyone with the link can view"
// without needing File → Publish to web
const CSV_URL = `https://docs.google.com/spreadsheets/d/${SHEET_ID}/gviz/tq?tqx=out:csv`;

function parseCSV(text) {
  const rows = [];
  for (const line of text.split(/\r?\n/)) {
    if (!line.trim()) continue;
    const cells = [];
    let cell = "", inQ = false;
    for (let i = 0; i < line.length; i++) {
      const c = line[i];
      if (c === '"') {
        if (inQ && line[i + 1] === '"') { cell += '"'; i++; }
        else inQ = !inQ;
      } else if (c === ',' && !inQ) { cells.push(cell); cell = ""; }
      else cell += c;
    }
    cells.push(cell);
    rows.push(cells);
  }
  return rows;
}

function col(headers, ...names) {
  for (const n of names) {
    const i = headers.indexOf(n.toLowerCase());
    if (i >= 0) return i;
  }
  return -1;
}

export default async function handler(req, res) {
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Cache-Control", "public, s-maxage=300, stale-while-revalidate=600");

  try {
    const r = await fetch(CSV_URL, {
      headers: { "User-Agent": "WAKE-CruiseTracker/1.0" },
    });

    if (!r.ok) throw new Error(`Sheet fetch ${r.status}`);
    const text = await r.text();

    // Detect Google sign-in redirect (sheet not public)
    if (text.includes("accounts.google.com") || text.includes("<html")) {
      throw new Error("Sheet not publicly accessible");
    }

    const rows = parseCSV(text);
    if (rows.length < 2) throw new Error("Empty sheet");

    const headers = rows[0].map(h => h.trim().toLowerCase().replace(/\s+/g, ""));

    const iPort    = col(headers, "port", "name");
    const iFlag    = col(headers, "flag");
    const iCountry = col(headers, "country");
    const iView    = col(headers, "camview", "cam_view", "description", "view");
    const iYtId    = col(headers, "ytid", "yt_id", "youtubeid", "youtube_id");
    const iLat     = col(headers, "plat", "lat", "latitude");
    const iLon     = col(headers, "plon", "plon", "lon", "lng", "longitude");
    const iSrc     = col(headers, "srcurl", "src_url", "url", "link");

    const get = (row, i) => (i >= 0 && row[i] != null ? row[i].trim() : "");

    const feeds = [];
    rows.slice(1).forEach((row, idx) => {
      const ytId = get(row, iYtId);
      const port = get(row, iPort);
      if (!ytId || !port) return; // skip rows without required fields
      const lat = parseFloat(get(row, iLat));
      const lon = parseFloat(get(row, iLon));
      feeds.push({
        id:      idx + 1,
        port,
        flag:    get(row, iFlag)    || "🌍",
        country: get(row, iCountry) || "",
        camView: get(row, iView)    || "",
        ytId,
        srcUrl:  get(row, iSrc)     || `https://www.youtube.com/live/${ytId}`,
        pLat:    isNaN(lat) ? null : lat,
        pLon:    isNaN(lon) ? null : lon,
      });
    });

    if (!feeds.length) throw new Error("No valid rows");

    res.status(200).json({ ok: true, feeds, source: "sheet", ts: Date.now() });

  } catch (err) {
    // Return error so the app knows to use its hardcoded fallback
    res.status(200).json({ ok: false, error: err.message });
  }
}
