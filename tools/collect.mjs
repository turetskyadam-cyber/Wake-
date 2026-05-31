// Collects current AIS positions for the fleet and merges them into positions.json.
// Run by .github/workflows/snapshot.yml on a schedule so coverage accumulates over
// time (different ships broadcast at different times). MMSIs are read straight from
// index.html so this stays in sync with the fleet automatically.
import fs from "fs";
import WebSocket from "ws";

const KEY = process.env.AISSTREAM_KEY || "54bc041923cc2216c2c25e250cfd61cf34946712";
const DURATION = (parseInt(process.env.COLLECT_SECONDS || "240", 10)) * 1000;

const html = fs.readFileSync("index.html", "utf8");
const MMSIS = [...new Set([...html.matchAll(/\["(\d{9})"/g)].map(m => m[1]))];
const CURRENT = new Set(MMSIS);
const BOXES = [[[-85,-180],[85,-120]],[[-85,-120],[85,-60]],[[-85,-60],[85,0]],
               [[-85,0],[85,60]],[[-85,60],[85,120]],[[-85,120],[85,180]]];
const CHUNK = 105;
const chunks = [];
for (let i = 0; i < MMSIS.length; i += CHUNK) chunks.push(MMSIS.slice(i, i + CHUNK));

const seed = {};
function open(chunk) {
  const ws = new WebSocket("wss://stream.aisstream.io/v0/stream");
  ws.on("open", () => ws.send(JSON.stringify({
    APIKey: KEY, BoundingBoxes: BOXES, FiltersShipMMSI: chunk, FilterMessageTypes: ["PositionReport"]
  })));
  ws.on("message", data => {
    let m; try { m = JSON.parse(data.toString()); } catch (e) { return; }
    if (m.error || m.MessageType !== "PositionReport") return;
    const p = m.Message.PositionReport, mmsi = String(m.MetaData.MMSI);
    if (typeof p.Latitude !== "number" || Math.abs(p.Latitude) > 90) return;
    const sog = (typeof p.Sog === "number" && p.Sog < 102.3) ? p.Sog : 0;
    const ns = p.NavigationalStatus, port = (ns === 1 || ns === 5 || sog < 0.5) ? 1 : 0;
    const hdg = (typeof p.TrueHeading === "number" && p.TrueHeading !== 511)
      ? p.TrueHeading : (typeof p.Cog === "number" ? Math.round(p.Cog) : 0);
    seed[mmsi] = [+p.Latitude.toFixed(4), +p.Longitude.toFixed(4), port, Math.round(hdg), +sog.toFixed(1)];
  });
  ws.on("error", () => {});
  return ws;
}

const sockets = chunks.map(open);
console.log(`Listening for ${MMSIS.length} MMSIs across ${chunks.length} connections for ${DURATION/1000}s…`);
setTimeout(() => {
  sockets.forEach(ws => { try { ws.close(); } catch (e) {} });
  let prev = {};
  try { prev = (JSON.parse(fs.readFileSync("positions.json", "utf8")).s) || {}; } catch (e) {}
  const merged = { ...prev, ...seed };            // newest position wins
  const out = {};
  for (const k of Object.keys(merged)) if (CURRENT.has(k)) out[k] = merged[k];  // keep only current fleet
  fs.writeFileSync("positions.json", JSON.stringify({ t: Date.now(), s: out }));
  console.log(`Captured ${Object.keys(seed).length} this run; snapshot now covers ${Object.keys(out).length}/${MMSIS.length} ships.`);
  process.exit(0);
}, DURATION);
