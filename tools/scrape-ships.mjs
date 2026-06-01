// Scrapes ship specs from Wikipedia for every ship in the WAKE fleet.
// Writes ships.json: { "Ship Name": { built, ton, pax, crew, length, shipyard, flag, photo, wiki } }
// Run by .github/workflows/ships.yml monthly.
import fs from "fs";

const html = fs.readFileSync("index.html", "utf8");
// Extract ship names from FLEET array: ["mmsi","Ship Name","Cruise Line"]
const SHIPS = [...new Set([...html.matchAll(/\["\d{9}","([^"]+)","[^"]+"\]/g)].map(m => m[1]))];
console.log(`Scraping ${SHIPS.length} ships…`);

const existing = fs.existsSync("ships.json") ? JSON.parse(fs.readFileSync("ships.json","utf8")) : {};
const out = {...existing};

async function sleep(ms){ return new Promise(r=>setTimeout(r,ms)); }

async function searchWiki(name){
  const q = encodeURIComponent(name + " cruise ship");
  const url = `https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch=${q}&srlimit=1&format=json&origin=*`;
  const r = await fetch(url).then(r=>r.json()).catch(()=>null);
  return r?.query?.search?.[0]?.title || null;
}

function parseInfobox(html){
  const spec = {};
  const extract = (key, ...patterns) => {
    for(const p of patterns){
      const m = html.match(p);
      if(m){ spec[key] = m[1].replace(/<[^>]+>/g,"").replace(/&nbsp;/g," ").replace(/\[\d+\]/g,"").trim(); break; }
    }
  };
  extract("built",     /[Ll]aid down.*?(\d{4})|[Bb]uilt.*?(\d{4})|[Cc]ompleted.*?(\d{4})|class="infobox-data"[^>]*>\s*(\d{4})\s*(?:<.*?)?<\/td>\s*<\/tr>\s*<tr[^>]*>\s*<th[^>]*>(?:[Ll]aunched|[Dd]elivered)/);
  extract("ton",       /[Gg]ross tonnage.*?(\d[\d,]+)/s, /tonnage.*?(\d[\d,]+)/s);
  extract("pax",       /[Cc]apacity.*?(\d[\d,]+)/s, /[Pp]assengers.*?(\d[\d,]+)/s);
  extract("crew",      /[Cc]rew.*?(\d[\d,]+)/s);
  extract("length",    /[Ll]ength.*?([\d,.]+)\s*m/s);
  extract("shipyard",  /[Bb]uilt by[^<]*<[^>]+>([^<]+)<\/a>/i, /[Bb]uilder[^<]*<[^>]+>([^<]+)<\/a>/i);
  extract("flag",      /[Ff]lag.*?<[^>]+>([^<]+)<\/a>/s);
  // normalise numbers
  if(spec.ton) spec.ton = parseInt(spec.ton.replace(/[^0-9]/g,"")) || null;
  if(spec.pax) spec.pax = parseInt(spec.pax.replace(/[^0-9]/g,"")) || null;
  if(spec.crew) spec.crew = parseInt(spec.crew.replace(/[^0-9]/g,"")) || null;
  if(spec.length) spec.length = parseFloat(spec.length.replace(/,/g,"")) || null;
  if(spec.built){
    // grab the 4-digit year
    const ym = spec.built.match(/(\d{4})/); spec.built = ym ? parseInt(ym[1]) : null;
  }
  return spec;
}

async function fetchWikiPage(title){
  const url = `https://en.wikipedia.org/w/api.php?action=parse&page=${encodeURIComponent(title)}&prop=text&format=json&origin=*`;
  const r = await fetch(url).then(r=>r.json()).catch(()=>null);
  if(!r?.parse?.text?.["*"]) return null;
  return r.parse.text["*"];
}

function extractPhoto(html){
  // Try to find the first image in the infobox
  const m = html.match(/class="[^"]*infobox[^"]*"[\s\S]*?<img[^>]+src="(\/\/upload\.wikimedia\.org\/[^"]+)"/);
  if(m) return "https:" + m[1];
  return null;
}

for(const name of SHIPS){
  if(out[name]?.built && out[name]?.ton) { console.log(`  skip ${name} (cached)`); continue; }
  await sleep(600);
  try{
    const title = await searchWiki(name);
    if(!title){ console.log(`  ? ${name}: no wiki match`); continue; }
    const pageHtml = await fetchWikiPage(title);
    if(!pageHtml){ console.log(`  ? ${name}: no page html`); continue; }
    const spec = parseInfobox(pageHtml);
    spec.photo = extractPhoto(pageHtml);
    spec.wiki = `https://en.wikipedia.org/wiki/${encodeURIComponent(title)}`;
    out[name] = {...(out[name]||{}), ...spec};
    const fields = Object.entries(spec).filter(([k,v])=>v).map(([k])=>k).join(",");
    console.log(`  ✓ ${name} [${fields}]`);
  }catch(e){
    console.log(`  ✗ ${name}: ${e.message}`);
  }
}

fs.writeFileSync("ships.json", JSON.stringify(out, null, 2));
console.log(`Done. ${Object.keys(out).length} ships in ships.json`);
