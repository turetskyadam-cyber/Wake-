// Scrapes ship specs from CruiseMapper.com for every ship in the WAKE fleet.
// Falls back to Wikipedia for any ship not found on CruiseMapper.
// Writes ships.json: { "Ship Name": { built, ton, pax, crew, length, shipyard, flag, photo, wiki } }
import fs from "fs";

const html = fs.readFileSync("index.html", "utf8");
// Extract [mmsi, name] pairs from FLEET array
const FLEET = [...html.matchAll(/\["(\d{9})","([^"]+)","[^"]+"\]/g)].map(m=>({mmsi:m[1],name:m[2]}));
const SHIPS = [...new Map(FLEET.map(s=>[s.name,s])).values()]; // dedupe by name
console.log(`Scraping ${SHIPS.length} ships…`);

const existing = fs.existsSync("ships.json") ? JSON.parse(fs.readFileSync("ships.json","utf8")) : {};
const out = {...existing};

const HEADERS = {
  "User-Agent":"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
  "Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
  "Accept-Language":"en-US,en;q=0.9",
};

async function sleep(ms){ return new Promise(r=>setTimeout(r,ms)); }
async function get(url){ return fetch(url,{headers:HEADERS}).then(r=>r.text()).catch(()=>null); }

// ── CruiseMapper ──────────────────────────────────────────────────────────────
async function searchCruiseMapper(name){
  const slug = name.toLowerCase().replace(/[^a-z0-9]+/g,"-").replace(/^-|-$/g,"");
  // Try direct slug URL first (most ships follow this pattern)
  const directUrl = `https://www.cruisemapper.com/ships/${slug}`;
  let page = await get(directUrl);
  if(page && page.includes("cruisemapper") && !page.includes("404") && page.includes("Gross Tonnage")){
    return {url:directUrl, html:page};
  }
  // Search CruiseMapper
  await sleep(300);
  const q = encodeURIComponent(name);
  const searchPage = await get(`https://www.cruisemapper.com/?q=${q}`);
  if(!searchPage) return null;
  // Find first ship result link
  const linkMatch = searchPage.match(/href="(\/ships\/[^"]+)"[^>]*>[^<]*(?:ship|vessel|cruise)/i)
    || searchPage.match(/href="(\/ships\/[^"]+)"/);
  if(!linkMatch) return null;
  const url = `https://www.cruisemapper.com${linkMatch[1]}`;
  await sleep(300);
  const shipPage = await get(url);
  if(!shipPage) return null;
  return {url, html:shipPage};
}

function parseCruiseMapper(html, name){
  const spec={};
  const grab=(label)=>{
    // Look for table row with this label
    const re=new RegExp(`${label}[^<]*<\\/[^>]+>\\s*<[^>]+>([^<]{1,80})`,"i");
    const m=html.match(re);
    return m ? m[1].replace(/&nbsp;/g," ").replace(/&amp;/g,"&").trim() : null;
  };
  const num=(s)=>s?parseInt(s.replace(/[^0-9]/g,""))||null:null;
  const flt=(s)=>s?parseFloat(s.replace(/[^0-9.]/g,""))||null:null;

  const ton=grab("Gross Tonnage")||grab("Gross tons")||grab("GRT");
  if(ton) spec.ton=num(ton);

  const built=grab("Year Built")||grab("Built")||grab("Delivered")||grab("Launched");
  if(built){ const ym=built.match(/(\d{4})/); if(ym) spec.built=parseInt(ym[1]); }

  const pax=grab("Passenger Capacity")||grab("Passengers")||grab("Capacity");
  if(pax) spec.pax=num(pax);

  const crew=grab("Crew")||grab("Officers");
  if(crew) spec.crew=num(crew);

  const len=grab("Length")||grab("Overall Length");
  if(len){ const lm=len.match(/([\d.]+)\s*m/); spec.length=lm?parseFloat(lm[1]):flt(len); }

  const yard=grab("Shipyard")||grab("Builder")||grab("Built by");
  if(yard) spec.shipyard=yard.replace(/<[^>]+>/g,"").trim();

  const flag=grab("Flag")||grab("Registry");
  if(flag) spec.flag=flag.trim();

  // Photo: CruiseMapper uses ship images
  const photoMatch=html.match(/src="(https?:\/\/[^"]+cruisemapper[^"]+\.(jpg|jpeg|png|webp))"/i)
    || html.match(/<img[^>]+class="[^"]*ship[^"]*"[^>]+src="([^"]+)"/i)
    || html.match(/property="og:image"\s+content="([^"]+)"/i);
  if(photoMatch) spec.photo=photoMatch[1];

  return spec;
}

// ── Wikipedia fallback ────────────────────────────────────────────────────────
async function fetchWikiPage(title){
  const url=`https://en.wikipedia.org/w/api.php?action=parse&page=${encodeURIComponent(title)}&prop=text&format=json&origin=*`;
  const r=await fetch(url).then(r=>r.json()).catch(()=>null);
  return r?.parse?.text?.["*"]||null;
}
async function searchWiki(name){
  // 1. Direct title
  let p=await fetchWikiPage(name); if(p) return {title:name,html:p};
  // 2. "(ship)" suffix
  p=await fetchWikiPage(name+" (ship)"); if(p) return {title:name+" (ship)",html:p};
  // 3. Search API
  const r=await fetch(`https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch=${encodeURIComponent(name)}&srlimit=2&format=json&origin=*`).then(r=>r.json()).catch(()=>null);
  for(const s of r?.query?.search||[]){
    p=await fetchWikiPage(s.title); if(p) return {title:s.title,html:p};
  }
  return null;
}
function parseWiki(html){
  const spec={};
  const box=(html.match(/class="[^"]*infobox[^"]*"([\s\S]+?)(?=<\/table>)/)||["",""])[1]||html;
  const grab=(...pats)=>{ for(const p of pats){ const m=box.match(p); if(m) for(let i=1;i<m.length;i++) if(m[i]) return m[i].replace(/<[^>]+>/g,"").replace(/&\w+;/g," ").replace(/\[\d+\]/g,"").replace(/\s+/g," ").trim(); } return null; };
  const ton=grab(/[Gg]ross tonnage[\s\S]{0,200}?(\d[\d,]+)/,/[Tt]onnage[\s\S]{0,200}?(\d[\d,]+)/);
  if(ton) spec.ton=parseInt(ton.replace(/[^0-9]/g,""))||null;
  const built=grab(/(?:[Dd]elivered|[Cc]ompleted|[Ee]ntered service)[\s\S]{0,200}?(\d{4})/,/(?:[Ll]aunched|[Bb]uilt)[\s\S]{0,200}?(\d{4})/);
  if(built){ const ym=built.match(/(\d{4})/); if(ym) spec.built=parseInt(ym[1]); }
  const pax=grab(/[Cc]apacity[\s\S]{0,300}?(\d[\d,]{2,})/,/[Pp]assengers[\s\S]{0,300}?(\d[\d,]{2,})/);
  if(pax) spec.pax=parseInt(pax.replace(/[^0-9]/g,""))||null;
  const crew=grab(/[Cc]rew[\s\S]{0,200}?(\d[\d,]+)/);
  if(crew) spec.crew=parseInt(crew.replace(/[^0-9]/g,""))||null;
  const len=grab(/[Ll]ength[\s\S]{0,100}?([\d,.]+)\s*m/);
  if(len) spec.length=parseFloat(len.replace(/,/g,""))||null;
  const yard=grab(/[Bb]uilt by[\s\S]{0,200}?>([^<]{3,40})</,/[Bb]uilder[\s\S]{0,200}?>([^<]{3,40})</);
  if(yard) spec.shipyard=yard;
  const flag=grab(/[Ff]lag[\s\S]{0,200}?>([^<]{3,30})</);
  if(flag) spec.flag=flag;
  const srcm=(html.match(/class="[^"]*infobox[^"]*"([\s\S]+?)(?=<\/table>)/)||["",""])[1]||"";
  const sm=srcm.match(/src="(\/\/upload\.wikimedia\.org\/[^"]+\.(jpg|jpeg|png|webp))"/)||html.match(/src="(\/\/upload\.wikimedia\.org\/[^"]+\.(jpg|jpeg|png|webp))"/);
  if(sm) spec.photo="https:"+sm[1].replace(/\/thumb\//,"/").replace(/\/\d+px-[^/]+$/,"");
  return spec;
}

// ── Main loop ─────────────────────────────────────────────────────────────────
let ok=0, skip=0, fail=0;
for(const {name} of SHIPS){
  if(out[name]?.built && out[name]?.ton){ skip++; process.stdout.write("."); continue; }
  await sleep(500);
  try{
    // Try CruiseMapper first
    const cm=await searchCruiseMapper(name);
    if(cm){
      const spec=parseCruiseMapper(cm.html,name);
      spec.cruisemapper=cm.url;
      // Also grab wiki for photo/extra if we lack photo
      if(!spec.photo){
        await sleep(300);
        const wk=await searchWiki(name);
        if(wk){
          const ws=parseWiki(wk.html);
          if(ws.photo) spec.photo=ws.photo;
          spec.wiki=`https://en.wikipedia.org/wiki/${encodeURIComponent(wk.title.replace(/ /g,"_"))}`;
        }
      }
      out[name]={...(out[name]||{}),...spec};
      const fields=Object.entries(spec).filter(([k,v])=>v).map(([k])=>k).join(",");
      console.log(`\n  ✓ ${name} [${fields||"url only"}]`);
      ok++;
    } else {
      // Fall back to Wikipedia
      await sleep(200);
      const wk=await searchWiki(name);
      if(wk){
        const spec=parseWiki(wk.html);
        spec.wiki=`https://en.wikipedia.org/wiki/${encodeURIComponent(wk.title.replace(/ /g,"_"))}`;
        out[name]={...(out[name]||{}),...spec};
        const fields=Object.entries(spec).filter(([k,v])=>v).map(([k])=>k).join(",");
        console.log(`\n  ~ ${name} (wiki) [${fields||"wiki only"}]`);
        ok++;
      } else {
        console.log(`\n  ? ${name}: not found`);
        fail++;
      }
    }
  }catch(e){
    console.log(`\n  ✗ ${name}: ${e.message}`);
    fail++;
  }
}

fs.writeFileSync("ships.json", JSON.stringify(out, null, 2));
console.log(`\n\nDone. ✓${ok} scraped  ⏭${skip} cached  ✗${fail} failed  →  ${Object.keys(out).length} total in ships.json`);
