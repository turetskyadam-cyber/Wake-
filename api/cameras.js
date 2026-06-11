// Fetches camera list from Google Sheet — only "name" and "url" columns required.
// Everything else (ytId, coordinates, flag, country) is derived automatically.

const SHEET_ID = "10F_8H8bPROFrSsVmhJ8oZ5yJS9IftpvKpViyMEIdVMk";
const CSV_URL  = `https://docs.google.com/spreadsheets/d/${SHEET_ID}/gviz/tq?tqx=out:csv`;

// ── Extract YouTube video ID from any YT URL format ─────────────────────────
function extractYtId(url) {
  if (!url) return null;
  url = url.trim();
  // Already just an ID (11 chars, no slashes)
  if (/^[A-Za-z0-9_-]{11}$/.test(url)) return url;
  const m =
    url.match(/[?&]v=([A-Za-z0-9_-]{11})/) ||
    url.match(/youtu\.be\/([A-Za-z0-9_-]{11})/) ||
    url.match(/\/live\/([A-Za-z0-9_-]{11})/) ||
    url.match(/\/embed\/([A-Za-z0-9_-]{11})/) ||
    url.match(/\/shorts\/([A-Za-z0-9_-]{11})/);
  return m ? m[1] : null;
}

// ── Country code → flag emoji ────────────────────────────────────────────────
function countryFlag(code) {
  if (!code || code.length !== 2) return "🌍";
  return code.toUpperCase().split("")
    .map(c => String.fromCodePoint(c.charCodeAt(0) + 127397))
    .join("");
}

// ── Geocode a port name via Nominatim (free, no key needed) ─────────────────
async function geocode(portName) {
  try {
    const q = encodeURIComponent(portName + " port");
    const url = `https://nominatim.openstreetmap.org/search?q=${q}&format=json&limit=1&addressdetails=1`;
    const r = await fetch(url, {
      headers: { "User-Agent": "WAKE-CruiseTracker/1.0 (wake-rose.vercel.app)" }
    });
    if (!r.ok) return null;
    const data = await r.json();
    if (!data.length) return null;
    const hit = data[0];
    const addr = hit.address || {};
    const countryCode = addr.country_code?.toUpperCase() || "";
    const country = [
      addr.city || addr.town || addr.state || addr.county || "",
      addr.country || ""
    ].filter(Boolean).join(", ");
    return {
      lat: parseFloat(hit.lat),
      lon: parseFloat(hit.lon),
      flag: countryFlag(countryCode),
      country,
    };
  } catch {
    return null;
  }
}

// ── Simple CSV parser (handles quoted fields) ────────────────────────────────
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

function colIdx(headers, ...names) {
  for (const n of names) {
    const i = headers.indexOf(n.toLowerCase().replace(/[\s_-]/g, ""));
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
    if (text.includes("accounts.google.com") || text.trim().startsWith("<")) {
      throw new Error("Sheet not public — share it with 'Anyone with the link can view'");
    }

    const rows = parseCSV(text);
    if (rows.length < 2) throw new Error("Sheet appears empty");

    const headers = rows[0].map(h => h.trim().toLowerCase().replace(/[\s_-]/g, ""));

    // Accept "name" or "port" for the port name column
    const iName = colIdx(headers, "name", "port", "portname");
    // Accept "url", "youtube", "link", "yturl", "youtubeurl"
    const iUrl  = colIdx(headers, "url", "youtube", "link", "yturl", "youtubeurl", "youtubelink");
    // Optional overrides the user can add if they want
    const iLat  = colIdx(headers, "lat", "plat", "latitude");
    const iLon  = colIdx(headers, "lon", "plon", "lng", "longitude");
    const iFlag = colIdx(headers, "flag");
    const iCntry= colIdx(headers, "country");
    const iView = colIdx(headers, "view", "camview", "description");

    if (iName < 0 || iUrl < 0) {
      throw new Error(`Sheet must have "name" and "url" columns. Found: ${headers.join(", ")}`);
    }

    const get = (row, i) => (i >= 0 && row[i] != null ? row[i].trim() : "");

    // Build raw entries
    const entries = rows.slice(1)
      .map(row => ({ name: get(row, iName), url: get(row, iUrl), row }))
      .filter(e => e.name && e.url);

    if (!entries.length) throw new Error("No valid rows (need name + url)");

    // Geocode all entries in parallel (Nominatim allows reasonable concurrency)
    const feeds = await Promise.all(entries.map(async (e, idx) => {
      const ytId = extractYtId(e.url);
      if (!ytId) return null; // skip bad URLs

      // Use sheet overrides if provided, otherwise geocode
      let lat = parseFloat(get(e.row, iLat));
      let lon = parseFloat(get(e.row, iLon));
      let flag = get(e.row, iFlag);
      let country = get(e.row, iCntry);

      if (isNaN(lat) || isNaN(lon) || !flag) {
        const geo = await geocode(e.name);
        if (geo) {
          if (isNaN(lat)) lat = geo.lat;
          if (isNaN(lon)) lon = geo.lon;
          if (!flag) flag = geo.flag;
          if (!country) country = geo.country;
        }
      }

      return {
        id:      idx + 1,
        port:    e.name,
        flag:    flag || "🌍",
        country: country || "",
        camView: get(e.row, iView) || `${e.name} live cam`,
        ytId,
        srcUrl:  `https://www.youtube.com/live/${ytId}`,
        pLat:    isNaN(lat) ? null : lat,
        pLon:    isNaN(lon) ? null : lon,
      };
    }));

    const valid = feeds.filter(Boolean);
    if (!valid.length) throw new Error("No entries with valid YouTube URLs");

    res.status(200).json({ ok: true, feeds: valid, source: "sheet", ts: Date.now() });

  } catch (err) {
    res.status(200).json({ ok: false, error: err.message });
  }
}
