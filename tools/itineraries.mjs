// Scrapes CruiseMapper port schedule pages and writes itineraries.json.
// Run by .github/workflows/itineraries.yml daily.
// Output: { generated, ports: { portName: [{s:ship, d:date, a:arr, e:dep}] } }
import fs from "fs";

const DELAY_MS = 1500; // polite crawl delay between requests

const PORTS = [
  // US Florida / Gulf
  {name:"PortMiami",            slug:"miami-port-40"},
  {name:"Port Everglades",      slug:"fort-lauderdale-port-44"},
  {name:"Port Canaveral",       slug:"port-canaveral-port-42"},
  {name:"Port Tampa Bay",       slug:"tampa-port-38"},
  {name:"Galveston",            slug:"galveston-port-88"},
  {name:"Port of New Orleans",  slug:"new-orleans-port-43"},
  {name:"Port of Mobile",       slug:"mobile-port-3301"},
  // US East Coast
  {name:"New York",             slug:"new-york-port-98"},
  {name:"Port of Baltimore",    slug:"baltimore-port-33"},
  {name:"Port of Boston",       slug:"boston-port-101"},
  // US West Coast / Pacific
  {name:"San Francisco",        slug:"san-francisco-port-2"},
  {name:"Los Angeles",          slug:"los-angeles-port-5"},
  {name:"Honolulu",             slug:"honolulu-port-84"},
  // Pacific Northwest / Canada
  {name:"Vancouver",            slug:"vancouver-port-4"},
  {name:"Seattle",              slug:"seattle-port-6"},
  // Alaska
  {name:"Juneau",               slug:"juneau-port-407"},
  // Caribbean — private islands & ports of call
  {name:"Nassau",               slug:"nassau-port-27"},
  {name:"Coco Cay",             slug:"coco-cay-port-392"},
  {name:"Cozumel",              slug:"cozumel-port-26"},
  {name:"Grand Cayman",         slug:"grand-cayman-island-port-25"},
  {name:"Roatan",               slug:"roatan-island-port-29"},
  {name:"Labadee",              slug:"labadee-haiti-port-824"},
  {name:"Amber Cove",           slug:"puerto-plata-amber-cove-port-1936"},
  {name:"Falmouth",             slug:"falmouth-jamaica-port-667"},
  {name:"Ocho Rios",            slug:"ocho-rios-port-708"},
  {name:"St. Thomas",           slug:"st-thomas-island-usvi-port-604"},
  {name:"St. Maarten",          slug:"philipsburg-st-maarten-port-594"},
  {name:"Aruba",                slug:"oranjestad-aruba-port-452"},
  {name:"Curaçao",              slug:"willemstad-curacao-port-31"},
  {name:"San Juan",             slug:"san-juan-port-39"},
  // Mediterranean
  {name:"Barcelona",            slug:"barcelona-port-82"},
  {name:"Piraeus",              slug:"piraeus-athens-port-80"},
  {name:"Dubrovnik",            slug:"dubrovnik-port-137"},
  // Northern Europe
  {name:"Southampton",          slug:"southampton-port-115"},
  {name:"Copenhagen",           slug:"copenhagen-port-58"},
  {name:"Amsterdam",            slug:"amsterdam-port-56"},
  // Asia
  {name:"Singapore",            slug:"singapore-port-10"},
];

function monthStr(offsetMonths = 0) {
  const d = new Date();
  d.setDate(1); // prevent day-of-month overflow (e.g. May 31 + 1 month = July 1)
  d.setMonth(d.getMonth() + offsetMonths);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

async function fetchPage(slug, month) {
  const url = `https://www.cruisemapper.com/ports/${slug}?month=${month}`;
  try {
    const res = await fetch(url, {
      headers: {
        "User-Agent": "Mozilla/5.0 (compatible; CruiseTrackerBot/1.0; +https://github.com/turetskyadam-cyber/Wake-)",
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
      },
      signal: AbortSignal.timeout(15000),
    });
    if (!res.ok) { console.warn(`  HTTP ${res.status} for ${slug} ${month}`); return ""; }
    return res.text();
  } catch (e) {
    console.warn(`  Fetch error for ${slug} ${month}: ${e.message}`);
    return "";
  }
}

function stripTags(s) {
  return s
    .replace(/<[^>]+>/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&nbsp;/g, " ")
    .replace(/&#\d+;/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

const MONTH_IDX = {
  january:0, february:1, march:2, april:3, may:4, june:5,
  july:6, august:7, september:8, october:9, november:10, december:11,
};

function parseSchedule(html) {
  const results = [];
  const rows = [...html.matchAll(/<tr[^>]*>([\s\S]*?)<\/tr>/gi)];
  let curDate = null;

  for (const [, rowHtml] of rows) {
    const cells = [...rowHtml.matchAll(/<td[^>]*>([\s\S]*?)<\/td>/gi)]
      .map(([, c]) => stripTags(c));

    if (cells.length < 2) continue;

    // Try to find a date in the first two cells
    for (const cell of cells.slice(0, 2)) {
      const m = cell.match(/(\d{1,2})\s+(january|february|march|april|may|june|july|august|september|october|november|december)[,\s]+(\d{4})/i);
      if (m) {
        const mon = MONTH_IDX[m[2].toLowerCase()];
        if (mon !== undefined) {
          curDate = `${m[3]}-${String(mon + 1).padStart(2, "0")}-${String(+m[1]).padStart(2, "0")}`;
        }
        break;
      }
    }

    if (!curDate) continue;

    // 4-cell row: [date, ship, arr, dep]
    // 3-cell row: [ship, arr, dep] (date rowspans from above)
    let ship, arr, dep;
    if (cells.length >= 4) {
      ship = cells[1]; arr = cells[2]; dep = cells[3];
    } else if (cells.length === 3) {
      ship = cells[0]; arr = cells[1]; dep = cells[2];
    } else {
      continue;
    }

    const isTime = s => /^\d{1,2}:\d{2}$/.test(s.trim());
    if (!isTime(arr) && !isTime(dep)) continue;
    if (!ship || ship.length < 3 || isTime(ship)) continue;

    // Ship name may include cruise line after a newline/tab — take first line only
    const shipName = ship.split(/[\n\t]/)[0].trim();
    if (!shipName || shipName.length < 3) continue;

    results.push({ s: shipName, d: curDate, a: arr.trim(), e: dep.trim() });
  }

  return results;
}

async function main() {
  const months = [monthStr(0), monthStr(1), monthStr(2)];
  const out = { generated: Date.now(), ports: {} };

  for (const port of PORTS) {
    const calls = [];
    for (const month of months) {
      const html = await fetchPage(port.slug, month);
      if (html) calls.push(...parseSchedule(html));
      await sleep(DELAY_MS);
    }
    // Deduplicate by ship+date
    const seen = new Set();
    const deduped = calls.filter(c => {
      const key = `${c.d}|${c.s.toLowerCase()}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
    if (deduped.length) out.ports[port.name] = deduped;
    console.log(`${port.name}: ${deduped.length} calls`);
  }

  fs.writeFileSync("itineraries.json", JSON.stringify(out));
  const total = Object.values(out.ports).reduce((n, v) => n + v.length, 0);
  console.log(`Done. ${Object.keys(out.ports).length} ports, ${total} total calls.`);
}

main().catch(e => { console.error(e); process.exit(1); });
