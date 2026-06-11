// Appends the latest positions.json fixes to per-day history files so the app
// can render real 7-day wake trails. Run by .github/workflows/snapshot.yml right
// after collect.mjs. Each history/YYYY-MM-DD.json maps mmsi -> array of
// [minutesSinceUtcMidnight, lat, lon, speedKn]. Stationary/stale fixes (same
// rounded lat/lon as the ship's last logged point) are skipped, so in-port ships
// and positions collect.mjs merely carried forward don't bloat the files.
// Files older than HISTORY_DAYS are pruned. Also regenerates fleet.json (slug,
// mmsi, name, line, color per ship) for shareable links, embeds and OG cards.
import fs from "fs";
import path from "path";

const HISTORY_DIR = "history";
const HISTORY_DAYS = 8;          // keep 8 files so 7 full days are always available
const now = new Date();

const dayKey = d => d.toISOString().slice(0, 10);
const today = dayKey(now);
const yesterday = dayKey(new Date(now.getTime() - 864e5));

function readJSON(file, fallback) {
  try { return JSON.parse(fs.readFileSync(file, "utf8")); } catch (e) { return fallback; }
}

// ---- append today's fixes -------------------------------------------------
const snap = readJSON("positions.json", null);
if (!snap || !snap.s) { console.error("positions.json missing or unreadable; nothing to append."); process.exit(1); }

fs.mkdirSync(HISTORY_DIR, { recursive: true });
const todayFile = path.join(HISTORY_DIR, `${today}.json`);
const day = readJSON(todayFile, {});
const prevDay = readJSON(path.join(HISTORY_DIR, `${yesterday}.json`), {});

const minuteNow = now.getUTCHours() * 60 + now.getUTCMinutes();
let appended = 0, skipped = 0;
for (const [mmsi, fix] of Object.entries(snap.s)) {
  const lat = +(+fix[0]).toFixed(3), lon = +(+fix[1]).toFixed(3), spd = +(+fix[4]).toFixed(1);
  if (!isFinite(lat) || !isFinite(lon) || Math.abs(lat) > 90 || Math.abs(lon) > 180) continue;
  const track = day[mmsi] || [];
  const last = track.length ? track[track.length - 1]
             : (prevDay[mmsi] && prevDay[mmsi].length ? prevDay[mmsi][prevDay[mmsi].length - 1] : null);
  if (last && last[1] === lat && last[2] === lon) { skipped++; continue; }
  track.push([minuteNow, lat, lon, spd]);
  day[mmsi] = track;
  appended++;
}
fs.writeFileSync(todayFile, JSON.stringify(day));
console.log(`History ${today}: appended ${appended}, skipped ${skipped} unchanged; file now ${fs.statSync(todayFile).size} bytes.`);

// ---- prune old day files ---------------------------------------------------
const cutoff = dayKey(new Date(now.getTime() - (HISTORY_DAYS - 1) * 864e5));
for (const f of fs.readdirSync(HISTORY_DIR)) {
  const m = f.match(/^(\d{4}-\d{2}-\d{2})\.json$/);
  if (m && m[1] < cutoff) { fs.unlinkSync(path.join(HISTORY_DIR, f)); console.log(`Pruned ${f}`); }
}

// ---- regenerate fleet.json from index.html ---------------------------------
const html = fs.readFileSync("index.html", "utf8");
const colors = {};
const linesBlock = html.match(/const LINES = \{([\s\S]*?)\};/);
if (linesBlock) for (const m of linesBlock[1].matchAll(/"([^"]+)"\s*:\s*"(#[0-9a-fA-F]{3,8})"/g)) colors[m[1]] = m[2];

const slugOf = n => n.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
const ships = [];
for (const m of html.matchAll(/\[\s*"(\d{9})"\s*,\s*"([^"]+)"\s*,\s*"([^"]+)"\s*\]/g)) {
  ships.push({ slug: slugOf(m[2]), mmsi: m[1], name: m[2], line: m[3], color: colors[m[3]] || "#8fb6c9" });
}
if (ships.length) {
  const prev = readJSON("fleet.json", null);
  const same = prev && JSON.stringify(prev.ships) === JSON.stringify(ships);
  if (!same) {
    fs.writeFileSync("fleet.json", JSON.stringify({ generated: Date.now(), ships }, null, 1));
    console.log(`fleet.json written (${ships.length} ships).`);
  } else {
    console.log(`fleet.json unchanged (${ships.length} ships).`);
  }
} else {
  console.warn("No FLEET rows matched in index.html; fleet.json not written.");
}
