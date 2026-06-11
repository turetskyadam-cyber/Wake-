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

// ── Known cruise ports — avoids geocoding ambiguity for common names ─────────
const KNOWN_PORTS = {
  "miami":            { lat:25.7742,  lon:-80.1728,  flag:"🇺🇸", country:"Florida, USA" },
  "key west":         { lat:24.5551,  lon:-81.8034,  flag:"🇺🇸", country:"Florida, USA" },
  "port canaveral":   { lat:28.4157,  lon:-80.6297,  flag:"🇺🇸", country:"Florida, USA" },
  "cape canaveral":   { lat:28.4157,  lon:-80.6297,  flag:"🇺🇸", country:"Florida, USA" },
  "galveston":        { lat:29.3013,  lon:-94.7977,  flag:"🇺🇸", country:"Texas, USA" },
  "new orleans":      { lat:29.9499,  lon:-90.0701,  flag:"🇺🇸", country:"Louisiana, USA" },
  "san diego":        { lat:32.7224,  lon:-117.1705, flag:"🇺🇸", country:"California, USA" },
  "los angeles":      { lat:33.7395,  lon:-118.2618, flag:"🇺🇸", country:"California, USA" },
  "long beach":       { lat:33.7395,  lon:-118.2618, flag:"🇺🇸", country:"California, USA" },
  "san francisco":    { lat:37.8080,  lon:-122.4177, flag:"🇺🇸", country:"California, USA" },
  "seattle":          { lat:47.6230,  lon:-122.3492, flag:"🇺🇸", country:"Washington, USA" },
  "baltimore":        { lat:39.2693,  lon:-76.5783,  flag:"🇺🇸", country:"Maryland, USA" },
  "new york":         { lat:40.6960,  lon:-74.0440,  flag:"🇺🇸", country:"New York, USA" },
  "boston":           { lat:42.3601,  lon:-71.0489,  flag:"🇺🇸", country:"Massachusetts, USA" },
  "fort lauderdale":  { lat:26.1004,  lon:-80.1132,  flag:"🇺🇸", country:"Florida, USA" },
  "tampa":            { lat:27.9474,  lon:-82.4544,  flag:"🇺🇸", country:"Florida, USA" },
  "jacksonville":     { lat:30.3322,  lon:-81.6557,  flag:"🇺🇸", country:"Florida, USA" },
  "vancouver":        { lat:49.2829,  lon:-123.1133, flag:"🇨🇦", country:"British Columbia, Canada" },
  "victoria":         { lat:48.4284,  lon:-123.3656, flag:"🇨🇦", country:"British Columbia, Canada" },
  "nassau":           { lat:25.0847,  lon:-77.3388,  flag:"🇧🇸", country:"Bahamas" },
  "st thomas":        { lat:18.3426,  lon:-64.9306,  flag:"🇻🇮", country:"US Virgin Islands" },
  "san juan":         { lat:18.4657,  lon:-66.1185,  flag:"🇵🇷", country:"Puerto Rico" },
  "cozumel":          { lat:20.5107,  lon:-86.9475,  flag:"🇲🇽", country:"Mexico" },
  "costa maya":       { lat:18.7270,  lon:-87.7060,  flag:"🇲🇽", country:"Mexico" },
  "progreso":         { lat:21.2952,  lon:-89.6640,  flag:"🇲🇽", country:"Mexico" },
  "ensenada":         { lat:31.8553,  lon:-116.6133, flag:"🇲🇽", country:"Mexico" },
  "cabo san lucas":   { lat:22.8905,  lon:-109.9167, flag:"🇲🇽", country:"Mexico" },
  "puerto vallarta":  { lat:20.6534,  lon:-105.2253, flag:"🇲🇽", country:"Mexico" },
  "cartagena":        { lat:10.3910,  lon:-75.4794,  flag:"🇨🇴", country:"Colombia" },
  "falmouth":         { lat:18.4958,  lon:-77.6588,  flag:"🇯🇲", country:"Jamaica" },
  "montego bay":      { lat:18.4762,  lon:-77.9129,  flag:"🇯🇲", country:"Jamaica" },
  "ocho rios":        { lat:18.4071,  lon:-77.1027,  flag:"🇯🇲", country:"Jamaica" },
  "george town":      { lat:19.2923,  lon:-81.3851,  flag:"🇰🇾", country:"Cayman Islands" },
  "grand cayman":     { lat:19.2923,  lon:-81.3851,  flag:"🇰🇾", country:"Cayman Islands" },
  "aruba":            { lat:12.5186,  lon:-70.0358,  flag:"🇦🇼", country:"Aruba" },
  "curacao":          { lat:12.1084,  lon:-68.9335,  flag:"🇨🇼", country:"Curaçao" },
  "barbados":         { lat:13.0969,  lon:-59.6145,  flag:"🇧🇧", country:"Barbados" },
  "st kitts":         { lat:17.3026,  lon:-62.7177,  flag:"🇰🇳", country:"St Kitts" },
  "st lucia":         { lat:14.0101,  lon:-60.9875,  flag:"🇱🇨", country:"St Lucia" },
  "st maarten":       { lat:18.0425,  lon:-63.0548,  flag:"🇸🇽", country:"St Maarten" },
  "antigua":          { lat:17.1274,  lon:-61.8468,  flag:"🇦🇬", country:"Antigua" },
  "tortola":          { lat:18.4286,  lon:-64.6186,  flag:"🇻🇬", country:"British Virgin Islands" },
  "dubrovnik":        { lat:42.6507,  lon:18.0944,   flag:"🇭🇷", country:"Croatia" },
  "split":            { lat:43.5047,  lon:16.4435,   flag:"🇭🇷", country:"Croatia" },
  "kotor":            { lat:42.4247,  lon:18.7712,   flag:"🇲🇪", country:"Montenegro" },
  "athens":           { lat:37.9667,  lon:23.7167,   flag:"🇬🇷", country:"Greece" },
  "piraeus":          { lat:37.9667,  lon:23.7167,   flag:"🇬🇷", country:"Greece" },
  "santorini":        { lat:36.3932,  lon:25.4615,   flag:"🇬🇷", country:"Greece" },
  "mykonos":          { lat:37.4467,  lon:25.3289,   flag:"🇬🇷", country:"Greece" },
  "venice":           { lat:45.4408,  lon:12.3155,   flag:"🇮🇹", country:"Italy" },
  "rome":             { lat:41.8919,  lon:12.5113,   flag:"🇮🇹", country:"Italy" },
  "civitavecchia":    { lat:42.0911,  lon:11.7944,   flag:"🇮🇹", country:"Italy" },
  "naples":           { lat:40.8358,  lon:14.2487,   flag:"🇮🇹", country:"Italy" },
  "barcelona":        { lat:41.3501,  lon:2.1648,    flag:"🇪🇸", country:"Spain" },
  "mallorca":         { lat:39.5670,  lon:2.6483,    flag:"🇪🇸", country:"Spain" },
  "palma":            { lat:39.5670,  lon:2.6483,    flag:"🇪🇸", country:"Spain" },
  "canary islands":   { lat:28.0997,  lon:-15.4167,  flag:"🇪🇸", country:"Spain" },
  "gran canaria":     { lat:28.0997,  lon:-15.4167,  flag:"🇪🇸", country:"Spain" },
  "tenerife":         { lat:28.4636,  lon:-16.2518,  flag:"🇪🇸", country:"Spain" },
  "lisbon":           { lat:38.7073,  lon:-9.1367,   flag:"🇵🇹", country:"Portugal" },
  "southampton":      { lat:50.8979,  lon:-1.4049,   flag:"🇬🇧", country:"England, UK" },
  "london":           { lat:51.5007,  lon:0.0227,    flag:"🇬🇧", country:"England, UK" },
  "dover":            { lat:51.1279,  lon:1.3134,    flag:"🇬🇧", country:"England, UK" },
  "dublin":           { lat:53.3473,  lon:-6.2297,   flag:"🇮🇪", country:"Ireland" },
  "amsterdam":        { lat:52.3833,  lon:4.9167,    flag:"🇳🇱", country:"Netherlands" },
  "rotterdam":        { lat:51.9244,  lon:4.4777,    flag:"🇳🇱", country:"Netherlands" },
  "hamburg":          { lat:53.5500,  lon:10.0167,   flag:"🇩🇪", country:"Germany" },
  "copenhagen":       { lat:55.6761,  lon:12.5683,   flag:"🇩🇰", country:"Denmark" },
  "oslo":             { lat:59.9139,  lon:10.7522,   flag:"🇳🇴", country:"Norway" },
  "bergen":           { lat:60.3913,  lon:5.3221,    flag:"🇳🇴", country:"Norway" },
  "geirangerfjord":   { lat:62.1008,  lon:7.2049,    flag:"🇳🇴", country:"Norway" },
  "narvik":           { lat:68.4342,  lon:17.4270,   flag:"🇳🇴", country:"Norway" },
  "narvik havn":      { lat:68.4342,  lon:17.4270,   flag:"🇳🇴", country:"Norway" },
  "reykjavik":        { lat:64.1355,  lon:-21.8954,  flag:"🇮🇸", country:"Iceland" },
  "helsinki":         { lat:60.1699,  lon:24.9384,   flag:"🇫🇮", country:"Finland" },
  "stockholm":        { lat:59.3293,  lon:18.0686,   flag:"🇸🇪", country:"Sweden" },
  "singapore":        { lat:1.2646,   lon:103.8198,  flag:"🇸🇬", country:"Singapore" },
  "hong kong":        { lat:22.2855,  lon:114.1577,  flag:"🇭🇰", country:"Hong Kong" },
  "tokyo":            { lat:35.6762,  lon:139.6503,  flag:"🇯🇵", country:"Japan" },
  "sydney":           { lat:-33.8568, lon:151.2153,  flag:"🇦🇺", country:"Australia" },
  "melbourne":        { lat:-37.8136, lon:144.9631,  flag:"🇦🇺", country:"Australia" },
  "auckland":         { lat:-36.8467, lon:174.7694,  flag:"🇳🇿", country:"New Zealand" },
  "buenos aires":     { lat:-34.6118, lon:-58.3730,  flag:"🇦🇷", country:"Argentina" },
  "rio de janeiro":   { lat:-22.9068, lon:-43.1729,  flag:"🇧🇷", country:"Brazil" },
  "dubai":            { lat:25.2048,  lon:55.2708,   flag:"🇦🇪", country:"UAE" },
  "abu dhabi":        { lat:24.4539,  lon:54.3773,   flag:"🇦🇪", country:"UAE" },
  "malta":            { lat:35.8980,  lon:14.5125,   flag:"🇲🇹", country:"Malta" },
  "valletta":         { lat:35.8980,  lon:14.5125,   flag:"🇲🇹", country:"Malta" },
};

// ── Geocode a port name — lookup table first, Nominatim fallback ─────────────
async function geocode(portName) {
  const key = portName.toLowerCase().trim();
  if (KNOWN_PORTS[key]) return KNOWN_PORTS[key];

  try {
    // Try "cruise port NAME" for specificity
    const q = encodeURIComponent("cruise port " + portName);
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
