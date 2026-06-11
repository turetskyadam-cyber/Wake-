// Shared fleet lookup for the share/OG functions. Reads fleet.json (generated
// by tools/append-history.mjs) from GitHub raw with a short in-memory cache.
// Underscore prefix = not deployed as an endpoint by Vercel.
// DATA_BRANCH: flip to "main" when the feature branch is merged.
const DATA_BRANCH = "claude/cruise-ship-tracking-nsefj4";
export const RAW = `https://raw.githubusercontent.com/turetskyadam-cyber/Wake-/${DATA_BRANCH}/`;

let _cache = { ts: 0, ships: null };

export async function getFleet() {
  if (_cache.ships && Date.now() - _cache.ts < 10 * 60 * 1000) return _cache.ships;
  try {
    const r = await fetch(RAW + "fleet.json");
    if (r.ok) {
      const j = await r.json();
      if (j && Array.isArray(j.ships)) _cache = { ts: Date.now(), ships: j.ships };
    }
  } catch (e) {}
  return _cache.ships || [];
}

export async function getShip(q) {
  if (!q) return null;
  const key = String(q).toLowerCase().trim();
  const ships = await getFleet();
  return ships.find(s => s.slug === key || s.mmsi === key) || null;
}

export async function getStatus(mmsi) {
  try {
    const r = await fetch(RAW + "positions.json");
    if (!r.ok) return null;
    const snap = await r.json();
    const fix = snap && snap.s && snap.s[mmsi];
    if (!fix) return null;
    return { lat: fix[0], lon: fix[1], inPort: !!fix[2], hdg: fix[3], spd: fix[4] };
  } catch (e) { return null; }
}
