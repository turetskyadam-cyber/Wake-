#!/usr/bin/env python3
"""
CruiseDig itinerary scraper for WAKE fleet tracker.
Scrapes https://cruisedig.com for cruise ship itineraries, stores data in
SQLite, then exports itineraries.json in the format the browser app expects.

Usage:
  python tools/scraper.py              # start scheduler (runs every 24 h)
  python tools/scraper.py --run-now    # run immediately and exit
"""

import argparse
import json
import logging
import random
import re
import sqlite3
import time
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests
from apscheduler.schedulers.blocking import BlockingScheduler
from bs4 import BeautifulSoup

# ── Configuration ────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "cruisedig.db"
ITIN_JSON_PATH = BASE_DIR / "itineraries.json"
SLUGS_CACHE_PATH = BASE_DIR / "ship_slugs.json"
LOG_PATH = BASE_DIR / "scraper.log"

BASE_URL = "https://cruisedig.com"
SHIPS_TOTAL_PAGES = 15        # pages 0–14 ≈ 285 ships
PORT_STOP_HORIZON_DAYS = 90   # only fetch AJAX port-stop detail for voyages starting within this window
MAX_AJAX_PER_SHIP = 3         # cap: fetch port-stop detail for at most this many voyages per ship
                              # keeps total AJAX calls to ~855 (285 ships × 3) and avoids rate-limiting

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; CruiseItineraryScraper/1.0)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Mapping from CruiseDig port names (lowercased, stripped) to WAKE CRUISE_PORTS names.
# CruiseDig uses "City, State/Country" format; keys cover both full and city-only forms.
PORT_MAP: dict[str, str] = {
    # Florida / Gulf
    "miami": "PortMiami",
    "miami, florida": "PortMiami",
    "port miami": "PortMiami",
    "miami, fl": "PortMiami",
    "fort lauderdale": "Port Everglades",
    "port everglades": "Port Everglades",
    "fort lauderdale, florida": "Port Everglades",
    "port canaveral": "Port Canaveral",
    "port canaveral, florida": "Port Canaveral",
    "canaveral": "Port Canaveral",
    "cape canaveral": "Port Canaveral",
    "tampa": "Port Tampa Bay",
    "port tampa bay": "Port Tampa Bay",
    "tampa, florida": "Port Tampa Bay",
    "galveston": "Galveston",
    "galveston, texas": "Galveston",
    "new orleans": "Port of New Orleans",
    "new orleans, louisiana": "Port of New Orleans",
    "mobile": "Port of Mobile",
    "mobile, alabama": "Port of Mobile",
    # US East Coast
    "new york": "New York",
    "new york, nyc manhattan, brooklyn": "New York",
    "new york, new york": "New York",
    "brooklyn": "New York",
    "manhattan": "New York",
    "baltimore": "Port of Baltimore",
    "baltimore, maryland": "Port of Baltimore",
    "boston": "Port of Boston",
    "boston, massachusetts": "Port of Boston",
    # US West Coast / Pacific
    "san francisco": "San Francisco",
    "san francisco, california": "San Francisco",
    "los angeles": "Los Angeles",
    "los angeles, california": "Los Angeles",
    "long beach": "Los Angeles",
    "long beach, california": "Los Angeles",
    "honolulu": "Honolulu",
    "honolulu, hawaii": "Honolulu",
    # Pacific Northwest / Canada
    "vancouver": "Vancouver",
    "vancouver, canada": "Vancouver",
    "seattle": "Seattle",
    "seattle, washington": "Seattle",
    # Alaska
    "juneau": "Juneau",
    "juneau, alaska": "Juneau",
    # Caribbean
    "nassau": "Nassau",
    "nassau, bahamas": "Nassau",
    "coco cay": "Coco Cay",
    "perfect day at coco cay": "Coco Cay",
    "cozumel": "Cozumel",
    "cozumel, mexico": "Cozumel",
    "grand cayman": "Grand Cayman",
    "george town": "Grand Cayman",
    "george town, cayman islands": "Grand Cayman",
    "roatan": "Roatan",
    "roatan, honduras": "Roatan",
    "labadee": "Labadee",
    "labadee, haiti": "Labadee",
    "amber cove": "Amber Cove",
    "puerto plata": "Amber Cove",
    "falmouth": "Falmouth",
    "falmouth, jamaica": "Falmouth",
    "ocho rios": "Ocho Rios",
    "ocho rios, jamaica": "Ocho Rios",
    "st. thomas": "St. Thomas",
    "saint thomas": "St. Thomas",
    "st thomas": "St. Thomas",
    "charlotte amalie": "St. Thomas",
    "st. thomas, us virgin islands": "St. Thomas",
    "st. maarten": "St. Maarten",
    "saint maarten": "St. Maarten",
    "philipsburg": "St. Maarten",
    "philipsburg, st. maarten": "St. Maarten",
    "aruba": "Aruba",
    "oranjestad": "Aruba",
    "oranjestad, aruba": "Aruba",
    "curacao": "Curaçao",
    "curaçao": "Curaçao",
    "willemstad": "Curaçao",
    "willemstad, curaçao": "Curaçao",
    "san juan": "San Juan",
    "san juan, puerto rico": "San Juan",
    # Mediterranean – Spain / Portugal / Atlantic Islands
    "barcelona": "Barcelona",
    "barcelona, spain": "Barcelona",
    "palma": "Palma de Mallorca",
    "palma de mallorca": "Palma de Mallorca",
    "palma de mallorca, spain": "Palma de Mallorca",
    "lisbon": "Lisbon",
    "lisbon, portugal": "Lisbon",
    "lisbonne": "Lisbon",
    "funchal": "Funchal",
    "funchal, madeira": "Funchal",
    "funchal (madeira)": "Funchal",
    "las palmas": "Las Palmas",
    "las palmas, gran canaria": "Las Palmas",
    "las palmas de gran canaria": "Las Palmas",
    "tenerife": "Santa Cruz de Tenerife",
    "santa cruz de tenerife": "Santa Cruz de Tenerife",
    "cadiz": "Cádiz",
    "cádiz": "Cádiz",
    "cadiz, spain": "Cádiz",
    "ibiza": "Ibiza",
    "ibiza, spain": "Ibiza",
    "malaga": "Malaga",
    "málaga": "Malaga",
    "malaga, spain": "Malaga",
    "alicante": "Alicante",
    "alicante, spain": "Alicante",
    "mahon": "Mahon",
    "mahón": "Mahon",
    "toulon": "Toulon",
    "toulon, france": "Toulon",
    "marseille": "Marseille",
    "marseille, france": "Marseille",
    "nice": "Nice / Villefranche",
    "villefranche": "Nice / Villefranche",
    "nice (villefranche)": "Nice / Villefranche",
    "villefranche-sur-mer": "Nice / Villefranche",
    "monte carlo": "Monte Carlo",
    "monaco": "Monte Carlo",
    "genoa": "Genoa",
    "genoa, italy": "Genoa",
    "gênes": "Genoa",
    "savona": "Savona",
    "savona, italy": "Savona",
    "la spezia": "La Spezia",
    "livorno": "Livorno",
    "livorno, italy": "Livorno",
    "livourne": "Livorno",
    "florence (livorno)": "Livorno",
    "pisa (livorno)": "Livorno",
    "civitavecchia": "Civitavecchia",
    "civitavecchia (rome)": "Civitavecchia",
    "rome (civitavecchia)": "Civitavecchia",
    "naples": "Naples",
    "naples, italy": "Naples",
    "naple": "Naples",
    "palermo": "Palermo",
    "palermo, italy": "Palermo",
    "messina": "Messina",
    "messina, italy": "Messina",
    "catania": "Catania",
    "catania, italy": "Catania",
    "venice": "Venice",
    "venice, italy": "Venice",
    "venise": "Venice",
    "ravenna": "Ravenna",
    "ravenna, italy": "Ravenna",
    "ravenne": "Ravenna",
    "porto corsini": "Ravenna",
    "porto corsini (ravenna)": "Ravenna",
    "ancona": "Ancona",
    "ancona, italy": "Ancona",
    "bari": "Bari",
    "bari, italy": "Bari",
    "trieste": "Trieste",
    "trieste, italy": "Trieste",
    "cagliari": "Cagliari",
    "cagliari, sardinia": "Cagliari",
    "ajaccio": "Ajaccio",
    "ajaccio, corsica": "Ajaccio",
    "valletta": "Valletta",
    "valletta, malta": "Valletta",
    "malta": "Valletta",
    # Mediterranean – Greece
    "piraeus": "Piraeus",
    "piraeus-athens": "Piraeus",
    "piraeus-athens, greece": "Piraeus",
    "piraeus (athens)": "Piraeus",
    "athens": "Piraeus",
    "athens (piraeus)": "Piraeus",
    "santorini": "Santorini",
    "santorini (thira)": "Santorini",
    "fira": "Santorini",
    "mykonos": "Mykonos",
    "mykonos, greece": "Mykonos",
    "rhodes": "Rhodes",
    "rhodes, greece": "Rhodes",
    "corfu": "Corfu",
    "corfu, greece": "Corfu",
    "corfou": "Corfu",
    "katakolon": "Katakolon",
    "katakolon (olympia)": "Katakolon",
    "heraklion": "Heraklion",
    "heraklion (crete)": "Heraklion",
    "thessaloniki": "Thessaloniki",
    "thessaloniki, greece": "Thessaloniki",
    "kavala": "Kavala",
    "kavala, greece": "Kavala",
    "volos": "Volos",
    "volos, greece": "Volos",
    "zakynthos": "Zakynthos",
    "zante": "Zakynthos",
    "nafplion": "Nafplion",
    "nafplio": "Nafplion",
    # Mediterranean – Turkey
    "kusadasi": "Kusadasi",
    "kusadasi, turkey": "Kusadasi",
    "ephesus (kusadasi)": "Kusadasi",
    "istanbul": "Istanbul",
    "istanbul, turkey": "Istanbul",
    "bodrum": "Bodrum",
    "bodrum, turkey": "Bodrum",
    "izmir": "Izmir",
    "izmir, turkey": "Izmir",
    "antalya": "Antalya",
    "antalya, turkey": "Antalya",
    # Mediterranean – Adriatic / Balkans
    "dubrovnik": "Dubrovnik",
    "dubrovnik, croatia": "Dubrovnik",
    "split": "Split",
    "split, croatia": "Split",
    "kotor": "Kotor",
    "kotor, montenegro": "Kotor",
    "zadar": "Zadar",
    "zadar, croatia": "Zadar",
    "hvar": "Hvar",
    "hvar, croatia": "Hvar",
    "sibenik": "Sibenik",
    "šibenik": "Sibenik",
    # Mediterranean – North Africa / Middle East
    "la goulette": "La Goulette",
    "tunis (la goulette)": "La Goulette",
    "la goulette (tunis)": "La Goulette",
    "limassol": "Limassol",
    "limassol, cyprus": "Limassol",
    "haifa": "Haifa",
    "haifa, israel": "Haifa",
    "ashdod": "Ashdod",
    "ashdod (jerusalem)": "Ashdod",
    "alexandria": "Alexandria",
    "alexandria, egypt": "Alexandria",
    "aqaba": "Aqaba",
    "aqaba, jordan": "Aqaba",
    # Northern Europe
    "southampton": "Southampton",
    "southampton, england": "Southampton",
    "southampton, united kingdom": "Southampton",
    "dover": "Dover",
    "dover, england": "Dover",
    "tilbury": "Tilbury",
    "london (tilbury)": "Tilbury",
    "leith": "Leith (Edinburgh)",
    "leith (edinburgh)": "Leith (Edinburgh)",
    "edinburgh (leith)": "Leith (Edinburgh)",
    "amsterdam": "Amsterdam",
    "amsterdam, netherlands": "Amsterdam",
    "zeebrugge": "Zeebrugge",
    "bruges (zeebrugge)": "Zeebrugge",
    "hamburg": "Hamburg",
    "hamburg, germany": "Hamburg",
    "kiel": "Kiel",
    "warnemunde": "Warnemünde",
    "warnemünde": "Warnemünde",
    "copenhagen": "Copenhagen",
    "copenhagen, denmark": "Copenhagen",
    "oslo": "Oslo",
    "oslo, norway": "Oslo",
    "bergen": "Bergen",
    "bergen, norway": "Bergen",
    "stavanger": "Stavanger",
    "alesund": "Ålesund",
    "ålesund": "Ålesund",
    "geiranger": "Geiranger",
    "flam": "Flåm",
    "flåm": "Flåm",
    "tromso": "Tromsø",
    "tromsø": "Tromsø",
    "honningsvag": "Honningsvåg",
    "honningsvåg": "Honningsvåg",
    "stockholm": "Stockholm",
    "stockholm, sweden": "Stockholm",
    "nynashamn": "Nynäshamn",
    "nynäshamn": "Nynäshamn",
    "helsinki": "Helsinki",
    "helsinki, finland": "Helsinki",
    "tallinn": "Tallinn",
    "tallinn, estonia": "Tallinn",
    "riga": "Riga",
    "riga, latvia": "Riga",
    "st. petersburg": "St. Petersburg",
    "saint petersburg": "St. Petersburg",
    "reykjavik": "Reykjavik",
    "reykjavik, iceland": "Reykjavik",
    "le havre": "Le Havre",
    "le havre, france": "Le Havre",
    "paris (le havre)": "Le Havre",
    "dublin": "Dublin",
    "dublin, ireland": "Dublin",
    "invergordon": "Invergordon",
    "invergordon (edinburgh)": "Invergordon",
    "leixoes": "Leixões",
    "leixões": "Leixões",
    "porto (leixoes)": "Leixões",
    # US West Coast / Pacific
    "san francisco": "San Francisco",
    "san francisco, california": "San Francisco",
    "los angeles": "Los Angeles",
    "los angeles, california": "Los Angeles",
    "long beach": "Los Angeles",
    "long beach, california": "Los Angeles",
    "san diego": "San Diego",
    "san diego, california": "San Diego",
    "honolulu": "Honolulu",
    "honolulu, hawaii": "Honolulu",
    "ensenada": "Ensenada",
    "ensenada, mexico": "Ensenada",
    "puerto vallarta": "Puerto Vallarta",
    "cabo san lucas": "Cabo San Lucas",
    "mazatlan": "Mazatlán",
    "mazatlán": "Mazatlán",
    # Pacific Northwest / Canada
    "vancouver": "Vancouver",
    "vancouver, canada": "Vancouver",
    "victoria": "Victoria",
    "victoria, bc": "Victoria",
    "seattle": "Seattle",
    "seattle, washington": "Seattle",
    # Alaska
    "juneau": "Juneau",
    "juneau, alaska": "Juneau",
    "skagway": "Skagway",
    "ketchikan": "Ketchikan",
    "sitka": "Sitka",
    "haines": "Haines",
    "icy strait point": "Icy Strait Point",
    # Caribbean
    "nassau": "Nassau",
    "nassau, bahamas": "Nassau",
    "coco cay": "Coco Cay",
    "perfect day at coco cay": "Coco Cay",
    "cozumel": "Cozumel",
    "cozumel, mexico": "Cozumel",
    "grand cayman": "Grand Cayman",
    "george town": "Grand Cayman",
    "george town, cayman islands": "Grand Cayman",
    "roatan": "Roatan",
    "roatan, honduras": "Roatan",
    "labadee": "Labadee",
    "labadee, haiti": "Labadee",
    "amber cove": "Amber Cove",
    "puerto plata": "Amber Cove",
    "falmouth": "Falmouth",
    "falmouth, jamaica": "Falmouth",
    "ocho rios": "Ocho Rios",
    "ocho rios, jamaica": "Ocho Rios",
    "st. thomas": "St. Thomas",
    "saint thomas": "St. Thomas",
    "st thomas": "St. Thomas",
    "charlotte amalie": "St. Thomas",
    "st. maarten": "St. Maarten",
    "saint maarten": "St. Maarten",
    "philipsburg": "St. Maarten",
    "aruba": "Aruba",
    "oranjestad": "Aruba",
    "curacao": "Curaçao",
    "curaçao": "Curaçao",
    "willemstad": "Curaçao",
    "san juan": "San Juan",
    "san juan, puerto rico": "San Juan",
    "st. kitts": "St. Kitts",
    "basseterre": "St. Kitts",
    "antigua": "Antigua",
    "st. john's": "Antigua",
    "st. lucia": "St. Lucia",
    "castries": "St. Lucia",
    "barbados": "Barbados",
    "bridgetown": "Barbados",
    "dominica": "Dominica",
    "roseau": "Dominica",
    "martinique": "Martinique",
    "fort-de-france": "Martinique",
    "grenada": "Grenada",
    "st. george's": "Grenada",
    "trinidad": "Trinidad",
    "port of spain": "Trinidad",
    "tortola": "Tortola",
    "road town": "Tortola",
    "key west": "Key West",
    "key west, florida": "Key West",
    "costa maya": "Costa Maya",
    "costa maya, mexico": "Costa Maya",
    "progreso": "Progreso",
    "progreso, mexico": "Progreso",
    "la romana": "La Romana",
    "la romana, dominican republic": "La Romana",
    "samana": "Samana",
    "st. vincent": "St. Vincent",
    "kingstown": "St. Vincent",
    "guadeloupe": "Guadeloupe",
    "pointe-a-pitre": "Guadeloupe",
    "bonaire": "Bonaire",
    "kralendijk": "Bonaire",
    "half moon cay": "Half Moon Cay",
    "princess cays": "Princess Cays",
    "turks & caicos": "Turks & Caicos",
    "turks and caicos": "Turks & Caicos",
    "grand turk": "Turks & Caicos",
    "freeport": "Freeport",
    "freeport, bahamas": "Freeport",
    # South America
    "buenos aires": "Buenos Aires",
    "buenos aires, argentina": "Buenos Aires",
    "santos": "Santos",
    "rio de janeiro": "Rio de Janeiro",
    "rio de janeiro, brazil": "Rio de Janeiro",
    "montevideo": "Montevideo",
    "montevideo, uruguay": "Montevideo",
    "cartagena, colombia": "Cartagena",
    "cartagena de indias": "Cartagena",
    "manta": "Manta",
    "manta, ecuador": "Manta",
    "callao": "Callao",
    "lima (callao)": "Callao",
    "valparaiso": "Valparaiso",
    "valparaíso": "Valparaiso",
    "puerto montt": "Puerto Montt",
    "punta arenas": "Punta Arenas",
    "punta arenas, chile": "Punta Arenas",
    "ushuaia": "Ushuaia",
    "ushuaia, argentina": "Ushuaia",
    "puerto madryn": "Puerto Madryn",
    # Middle East / Indian Ocean
    "dubai": "Dubai",
    "dubai, uae": "Dubai",
    "abu dhabi": "Abu Dhabi",
    "muscat": "Muscat",
    "muscat, oman": "Muscat",
    "aqaba": "Aqaba",
    # Asia
    "singapore": "Singapore",
    "singapore, singapore": "Singapore",
    "hong kong": "Hong Kong",
    "hong kong, china": "Hong Kong",
    "yokohama": "Yokohama",
    "tokyo (yokohama)": "Yokohama",
    "tokyo": "Tokyo",
    "shanghai": "Shanghai",
    "shanghai, china": "Shanghai",
    "osaka": "Osaka",
    "kobe": "Kobe",
    "osaka/kobe": "Osaka",
    "busan": "Busan",
    "busan, south korea": "Busan",
    "ho chi minh city": "Ho Chi Minh City",
    "saigon": "Ho Chi Minh City",
    "bangkok": "Bangkok",
    "laem chabang": "Bangkok",
    "colombo": "Colombo",
    "colombo, sri lanka": "Colombo",
    "mumbai": "Mumbai",
    "bombay": "Mumbai",
    "cochin": "Cochin",
    "kochi": "Cochin",
    "phuket": "Phuket",
    "bali": "Bali (Benoa)",
    "benoa": "Bali (Benoa)",
    # Australia / Pacific
    "sydney": "Sydney",
    "sydney, australia": "Sydney",
    "melbourne": "Melbourne",
    "auckland": "Auckland",
    "auckland, new zealand": "Auckland",
    "noumea": "Noumea",
    "nouméa": "Noumea",
    "papeete": "Papeete",
    "papeete, tahiti": "Papeete",
    "suva": "Suva",
    "suva, fiji": "Suva",
    "cairns": "Cairns",
    "brisbane": "Brisbane",
    # Africa
    "cape town": "Cape Town",
    "cape town, south africa": "Cape Town",
}


# ── Logging ──────────────────────────────────────────────────────────────────

def setup_logging() -> None:
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        fh = logging.FileHandler(LOG_PATH)
        fh.setFormatter(fmt)
        ch = logging.StreamHandler()
        ch.setFormatter(fmt)
        logger.addHandler(fh)
        logger.addHandler(ch)


# ── Database ─────────────────────────────────────────────────────────────────

def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS ships (
            id              INTEGER PRIMARY KEY,
            slug            TEXT UNIQUE NOT NULL,
            name            TEXT,
            operator        TEXT,
            year_built      INTEGER,
            cabins          INTEGER,
            max_occupancy   INTEGER,
            gross_tonnage   INTEGER,
            length_m        REAL,
            speed_kn        REAL,
            last_scraped_at TEXT
        );
        CREATE TABLE IF NOT EXISTS home_ports (
            id        INTEGER PRIMARY KEY,
            ship_id   INTEGER NOT NULL,
            port_name TEXT,
            country   TEXT,
            FOREIGN KEY (ship_id) REFERENCES ships(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS voyages (
            id                  INTEGER PRIMARY KEY,
            ship_id             INTEGER NOT NULL,
            route_name          TEXT,
            departure_datetime  TEXT,
            return_datetime     TEXT,
            last_scraped_at     TEXT,
            FOREIGN KEY (ship_id) REFERENCES ships(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS port_stops (
            id                  INTEGER PRIMARY KEY,
            voyage_id           INTEGER NOT NULL,
            port_name           TEXT,
            country             TEXT,
            arrival_datetime    TEXT,
            departure_datetime  TEXT,
            stop_order          INTEGER,
            FOREIGN KEY (voyage_id) REFERENCES voyages(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_ships_slug   ON ships(slug);
        CREATE INDEX IF NOT EXISTS idx_voyages_ship ON voyages(ship_id);
        CREATE INDEX IF NOT EXISTS idx_stops_voyage ON port_stops(voyage_id);
        CREATE INDEX IF NOT EXISTS idx_stops_port   ON port_stops(port_name);
        CREATE INDEX IF NOT EXISTS idx_stops_arr    ON port_stops(arrival_datetime);
    """)
    conn.commit()
    conn.close()
    logging.info("Database ready: %s", DB_PATH)


# ── HTTP helpers ──────────────────────────────────────────────────────────────

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


def fetch_html(url: str, slug: str = "") -> str | None:
    try:
        resp = SESSION.get(url, timeout=20)
        resp.raise_for_status()
        return resp.text
    except requests.exceptions.RequestException as exc:
        logging.error("GET error [%s] %s — %s", slug or url, url, exc)
        return None


def fetch_views_ajax(view_name: str, display_id: str, args: str) -> list[dict] | None:
    """POST to Drupal Views AJAX endpoint; returns parsed command list."""
    url = f"{BASE_URL}/views/ajax"
    try:
        resp = SESSION.post(
            url,
            data={
                "view_name": view_name,
                "view_display_id": display_id,
                "view_args": args,
                "_drupal_ajax": "1",
            },
            headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"},
            timeout=20,
        )
        resp.raise_for_status()
        raw = resp.text.strip()
        # Drupal sometimes wraps response in <textarea>
        if raw.startswith("<"):
            soup = BeautifulSoup(raw, "lxml")
            ta = soup.find("textarea")
            raw = ta.string if ta else raw
        return resp.json() if resp.headers.get("content-type", "").startswith("application/json") else json.loads(raw)
    except Exception as exc:
        logging.error("AJAX error %s(%s): %s", display_id, args, exc)
        return None


def polite_sleep() -> None:
    time.sleep(random.uniform(1.0, 2.5))


# ── Step 1: Discover ships ────────────────────────────────────────────────────

def discover_ships() -> list[str]:
    """Paginate /ships?page=0..14 and collect ship slugs."""
    cached = _load_slug_cache()
    if cached:
        logging.info("Slug cache hit: %d ships (skipping discovery)", len(cached))
        return cached

    slugs: list[str] = []
    seen: set[str] = set()

    for page in range(SHIPS_TOTAL_PAGES):
        url = f"{BASE_URL}/ships?page={page}"
        logging.info("Discovering ships page %d/%d …", page + 1, SHIPS_TOTAL_PAGES)
        html = fetch_html(url, slug=f"ships-page-{page}")
        if not html:
            logging.warning("Skipping index page %d (fetch failed)", page)
            polite_sleep()
            continue

        soup = BeautifulSoup(html, "lxml")
        page_count = 0
        for a in soup.select("a[href]"):
            href = a.get("href", "")
            m = re.match(r"^/ships/([^/?#]+)$", href)
            if m:
                slug = m.group(1)
                if slug and slug not in seen:
                    slugs.append(slug)
                    seen.add(slug)
                    page_count += 1

        logging.info("  Page %d: +%d slugs (total %d)", page, page_count, len(slugs))
        polite_sleep()

    _save_slug_cache(slugs)
    logging.info("Discovery complete: %d ships", len(slugs))
    return slugs


def _load_slug_cache() -> list[str] | None:
    if not SLUGS_CACHE_PATH.exists():
        return None
    try:
        data = json.loads(SLUGS_CACHE_PATH.read_text())
        age_h = (time.time() - data.get("generated", 0) / 1000) / 3600
        if age_h < 24:
            slugs = data.get("slugs") or []
            return slugs if slugs else None
    except Exception:
        pass
    return None


def _save_slug_cache(slugs: list[str]) -> None:
    SLUGS_CACHE_PATH.write_text(
        json.dumps({"generated": int(time.time() * 1000), "slugs": slugs}, indent=2)
    )


# ── Number helpers ────────────────────────────────────────────────────────────

def _eu_int(text: str) -> int | None:
    """Parse European-format integer: '2.116' or '135.225' → 2116, 135225."""
    text = text.strip()
    # Remove known non-numeric suffixes (gt, kn, m, passengers …)
    text = re.sub(r"[a-zA-Z%°,\s]+$", "", text).strip()
    # European format: dots as thousands separators
    text = text.replace(".", "")
    m = re.search(r"-?\d+", text)
    if m:
        try:
            return int(m.group())
        except ValueError:
            pass
    return None


def _eu_float(text: str) -> float | None:
    """Parse European-format float: '324' or '22' → 324.0, 22.0."""
    text = re.sub(r"[a-zA-Z%°,\s]+$", "", text).strip()
    m = re.search(r"[\d.]+", text)
    if m:
        try:
            return float(m.group())
        except ValueError:
            pass
    return None


# ── Date helpers ──────────────────────────────────────────────────────────────

_MONTH_ABBR = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _stop_date(day_mon: str, voyage_dep_date: str) -> str | None:
    """
    Convert a port-stop date like "02 Jun" to "YYYY-MM-DD" using the voyage
    departure date to infer the correct year (handles Dec→Jan rollovers).
    """
    m = re.match(r"^(\d{1,2})\s+([A-Za-z]{3})", day_mon.strip())
    if not m:
        return None
    day = int(m.group(1))
    mo = _MONTH_ABBR.get(m.group(2).lower())
    if not mo:
        return None
    dep_year = int(voyage_dep_date[:4])
    dep_mon = int(voyage_dep_date[5:7])

    # Try this year first; if month makes no sense relative to departure, try +1
    candidate = date(dep_year, mo, day)
    dep_date_obj = date(dep_year, dep_mon, int(voyage_dep_date[8:10]))
    if candidate < dep_date_obj - timedelta(days=7):
        # port stop appears to be before departure — wrap to next year
        try:
            candidate = date(dep_year + 1, mo, day)
        except ValueError:
            pass
    return candidate.isoformat()


# ── Step 2: Parse port stops via Drupal Views AJAX ───────────────────────────

def fetch_port_stops(voyage_node_id: str, voyage_dep_date: str) -> list[dict]:
    """
    POST to /views/ajax for the 'itinerary_ports' display of cruise_itinerary view.
    Returns list of port-stop dicts: {port_name, country, arrival_datetime, departure_datetime, stop_order}.
    """
    commands = fetch_views_ajax("cruise_itinerary", "itinerary_ports", voyage_node_id)
    if not commands:
        return []

    stops: list[dict] = []
    for cmd in commands:
        if cmd.get("command") != "insert":
            continue
        html = cmd.get("data", "")
        if not html or not html.strip():
            continue

        soup = BeautifulSoup(html, "lxml")
        port_cards = soup.select(".card--schedule")
        if not port_cards:
            continue

        for i, card in enumerate(port_cards):
            # Port name from .card__title span or anchor text
            name_el = card.select_one(".card__title .field--name-title") or card.select_one(".card__title a")
            raw_name = name_el.get_text(strip=True) if name_el else None
            if not raw_name:
                continue

            # Split "City, Country/State"
            port_name, country = _split_port_country(raw_name)

            # Arrival: .schedule-arrival .date + .time
            arr_dt = _parse_stop_dt(card, "schedule-arrival", voyage_dep_date)
            # Departure: .schedule-departure .date + .time
            dep_dt = _parse_stop_dt(card, "schedule-departure", voyage_dep_date)

            stops.append({
                "port_name": port_name,
                "country": country,
                "arrival_datetime": arr_dt,
                "departure_datetime": dep_dt,
                "stop_order": i,
            })
        break  # first insert command with data is the ports list

    return stops


def _parse_stop_dt(card, cls: str, voyage_dep_date: str) -> str | None:
    """Extract 'YYYY-MM-DD HH:MM' from a .schedule-arrival/.schedule-departure block."""
    el = card.select_one(f".{cls}")
    if not el:
        return None
    date_el = el.select_one(".date")
    time_el = el.select_one(".time")
    date_raw = date_el.get_text(strip=True) if date_el else ""
    time_raw = time_el.get_text(strip=True) if time_el else ""
    d = _stop_date(date_raw, voyage_dep_date)
    if d:
        return f"{d} {time_raw}" if time_raw else d
    return None


def _split_port_country(raw: str) -> tuple[str, str | None]:
    """Split 'Los Angeles, California' → ('Los Angeles', 'California')."""
    if ", " in raw:
        idx = raw.index(", ")
        return raw[:idx].strip(), raw[idx + 2:].strip()
    return raw.strip(), None


# ── Step 2: Scrape ship detail page ──────────────────────────────────────────

def _field_text(soup, drupal_field: str) -> str | None:
    """Get text from a Drupal field element (strips label text)."""
    el = soup.select_one(f".field--name-{drupal_field}")
    if not el:
        return None
    # The actual value is in .field__item; fall back to the whole element text
    item = el.select_one(".field__item") or el
    # Strip any inline label (e.g. "Year built 2021" → just the value part)
    label_el = item.select_one(".field__label, label")
    if label_el:
        label_el.decompose()
    return item.get_text(" ", strip=True) or None


def scrape_ship(slug: str) -> dict | None:
    """
    Scrape https://cruisedig.com/ships/{slug}.
    Returns a dict with ship metadata, home_ports, and voyages (with port_stops).
    Returns None on fatal fetch failure.
    """
    base_url = f"{BASE_URL}/ships/{slug}"
    html = fetch_html(base_url, slug=slug)
    if not html:
        return None

    soup = BeautifulSoup(html, "lxml")

    # ── Ship name ──
    name_el = soup.select_one("h1.page-title, h1.node__title, h1")
    ship_name = name_el.get_text(strip=True) if name_el else slug.replace("-", " ").title()

    # ── Operator ──
    op_raw = _field_text(soup, "field-ship-cruise-line")
    # Strip "Operator " prefix if present
    operator = re.sub(r"^Operator\s+", "", op_raw or "").strip() or None

    # ── Specs — use exact Drupal field names ──
    def _spec_int(field: str) -> int | None:
        txt = _field_text(soup, field)
        if not txt:
            return None
        # Strip label words: "Year built 2021" → "2021"; "Cabins 2.116" → "2.116"
        # Remove leading words up to the first digit
        m = re.search(r"[\d.]+", txt)
        return _eu_int(m.group()) if m else None

    def _spec_float(field: str) -> float | None:
        txt = _field_text(soup, field)
        if not txt:
            return None
        m = re.search(r"[\d.]+", txt)
        return _eu_float(m.group()) if m else None

    year_built    = _spec_int("field-ship-year-built") or _spec_int("field-ship-built")
    cabins        = _spec_int("field-ship-cabins") or _spec_int("field-ship-staterooms")
    max_occupancy = _spec_int("field-ship-max-occupancy") or _spec_int("field-ship-occupancy") or _spec_int("field-ship-passengers")
    gross_tonnage = _spec_int("field-ship-gross-tonnage") or _spec_int("field-ship-tonnage")
    length_m      = _spec_float("field-ship-length")
    speed_kn      = _spec_float("field-ship-speed")

    # year_built edge case: it's always 4 digits so _eu_int won't mangle it,
    # but just in case the text was "2.021" we fix it
    if year_built and year_built < 1800:
        year_built = None

    # ── Home ports ──
    home_ports: list[dict] = []
    for a in soup.select(".block--ship-homeports a[href^='/ports/'], .view-ship-home-ports a[href^='/ports/']"):
        raw = a.get_text(strip=True)
        if raw and len(raw) > 2:
            pname, country = _split_port_country(raw)
            if not any(hp["port_name"] == pname for hp in home_ports):
                home_ports.append({"port_name": pname, "country": country})

    # ── Voyages ── paginate through all voyage pages
    today_iso = date.today().isoformat()
    horizon_iso = (date.today() + timedelta(days=PORT_STOP_HORIZON_DAYS)).isoformat()

    all_voyages: list[dict] = []
    current_url = base_url
    page_num = 0
    current_soup = soup
    # Shared mutable budget so the cap applies across all voyage pages for this ship
    ajax_budget = [MAX_AJAX_PER_SHIP]

    while True:
        if page_num > 0:
            html = fetch_html(current_url, slug=slug)
            if not html:
                break
            current_soup = BeautifulSoup(html, "lxml")

        page_voyages = _parse_voyage_cards(current_soup, slug, today_iso, horizon_iso, ajax_budget)
        all_voyages.extend(page_voyages)
        logging.info("  [%s] page %d → %d voyages (total %d, ajax budget left: %d)",
                     slug, page_num, len(page_voyages), len(all_voyages), ajax_budget[0])

        # Stop paginating once AJAX budget is spent — remaining pages only have
        # voyages we won't fetch port stops for anyway.
        if ajax_budget[0] == 0:
            break

        # Follow "Next" pager link
        next_link = current_soup.select_one(".pager__item--next a")
        if not next_link:
            break
        next_url = urljoin(current_url, next_link.get("href", ""))
        if not next_url or next_url == current_url:
            break

        current_url = next_url
        page_num += 1
        if page_num > 50:
            logging.warning("[%s] hit 50-page voyage cap", slug)
            break
        polite_sleep()

    return {
        "slug": slug,
        "name": ship_name,
        "operator": operator,
        "year_built": year_built,
        "cabins": cabins,
        "max_occupancy": max_occupancy,
        "gross_tonnage": gross_tonnage,
        "length_m": length_m,
        "speed_kn": speed_kn,
        "home_ports": home_ports,
        "voyages": all_voyages,
    }


def _parse_voyage_cards(soup, slug: str, today_iso: str, horizon_iso: str,
                        ajax_budget: list[int]) -> list[dict]:
    """
    Extract voyage blocks from a ship page and fetch port stops where needed.
    ajax_budget is a one-element mutable list [remaining_calls] shared across
    pagination pages so the cap is applied per-ship across all pages.
    """
    voyages: list[dict] = []

    for card in soup.select(".card--view-mode-cruise-ship-itinerary"):
        # Route name
        route_el = card.select_one(".card__title .field--name-title")
        route_name = route_el.get_text(strip=True) if route_el else None

        # Departure and return datetimes from <time datetime="...Z"> attributes
        time_els = card.select("time[datetime]")
        dep_dt = ret_dt = None
        if len(time_els) >= 1:
            dep_dt = _iso_from_time_el(time_els[0])
        if len(time_els) >= 2:
            ret_dt = _iso_from_time_el(time_els[1])

        # Extract cruise node ID from data-href for AJAX port-stop fetch
        voyage_node_id: str | None = None
        data_href = card.get("data-href", "")
        m = re.search(r"/(\d+)$", data_href)
        if m:
            voyage_node_id = m.group(1)

        # Fetch port stops via AJAX only for upcoming voyages within the horizon,
        # and only while we have AJAX budget remaining for this ship.
        port_stops: list[dict] = []
        if ajax_budget[0] > 0 and dep_dt and voyage_node_id:
            dep_date = dep_dt[:10]
            in_window = dep_date <= horizon_iso and (
                dep_date >= today_iso or (ret_dt and ret_dt[:10] >= today_iso)
            )
            if in_window:
                port_stops = fetch_port_stops(voyage_node_id, dep_date)
                ajax_budget[0] -= 1
                if port_stops:
                    logging.debug("    node %s: %d stops (budget left: %d)",
                                  voyage_node_id, len(port_stops), ajax_budget[0])
                polite_sleep()

        voyages.append({
            "route_name": route_name,
            "departure_datetime": dep_dt,
            "return_datetime": ret_dt,
            "port_stops": port_stops,
        })

    return voyages


def _iso_from_time_el(el) -> str | None:
    """Extract 'YYYY-MM-DD HH:MM' from a <time datetime="2026-06-01T15:30:00Z"> element."""
    dt_attr = el.get("datetime", "")
    m = re.match(r"^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})", dt_attr)
    if m:
        return f"{m.group(1)} {m.group(2)}"
    return None


# ── Step 3: Storage ───────────────────────────────────────────────────────────

def upsert_ship(data: dict) -> tuple[int, int, int]:
    """Write ship + all related data to SQLite. Returns (ship_id, voyage_count, stop_count)."""
    now = datetime.now(timezone.utc).isoformat()
    conn = get_db()
    try:
        cur = conn.cursor()

        # UPSERT ship record
        cur.execute("""
            INSERT INTO ships
                (slug, name, operator, year_built, cabins, max_occupancy,
                 gross_tonnage, length_m, speed_kn, last_scraped_at)
            VALUES
                (:slug, :name, :operator, :year_built, :cabins, :max_occupancy,
                 :gross_tonnage, :length_m, :speed_kn, :now)
            ON CONFLICT(slug) DO UPDATE SET
                name            = excluded.name,
                operator        = COALESCE(excluded.operator, ships.operator),
                year_built      = COALESCE(excluded.year_built, ships.year_built),
                cabins          = COALESCE(excluded.cabins, ships.cabins),
                max_occupancy   = COALESCE(excluded.max_occupancy, ships.max_occupancy),
                gross_tonnage   = COALESCE(excluded.gross_tonnage, ships.gross_tonnage),
                length_m        = COALESCE(excluded.length_m, ships.length_m),
                speed_kn        = COALESCE(excluded.speed_kn, ships.speed_kn),
                last_scraped_at = excluded.last_scraped_at
        """, {
            "slug": data["slug"], "name": data.get("name"),
            "operator": data.get("operator"), "year_built": data.get("year_built"),
            "cabins": data.get("cabins"), "max_occupancy": data.get("max_occupancy"),
            "gross_tonnage": data.get("gross_tonnage"), "length_m": data.get("length_m"),
            "speed_kn": data.get("speed_kn"), "now": now,
        })

        ship_id: int = cur.execute(
            "SELECT id FROM ships WHERE slug=?", (data["slug"],)
        ).fetchone()[0]

        # Home ports: full replace
        cur.execute("DELETE FROM home_ports WHERE ship_id=?", (ship_id,))
        for hp in data.get("home_ports", []):
            cur.execute(
                "INSERT INTO home_ports (ship_id, port_name, country) VALUES (?,?,?)",
                (ship_id, hp["port_name"], hp.get("country")),
            )

        # Voyages: full replace per ship (cascades to port_stops)
        cur.execute("DELETE FROM voyages WHERE ship_id=?", (ship_id,))

        voyage_count = stop_count = 0
        for voyage in data.get("voyages", []):
            cur.execute("""
                INSERT INTO voyages (ship_id, route_name, departure_datetime, return_datetime, last_scraped_at)
                VALUES (?,?,?,?,?)
            """, (
                ship_id,
                voyage.get("route_name"),
                voyage.get("departure_datetime"),
                voyage.get("return_datetime"),
                now,
            ))
            voyage_id = cur.lastrowid
            voyage_count += 1

            for stop in voyage.get("port_stops", []):
                cur.execute("""
                    INSERT INTO port_stops
                        (voyage_id, port_name, country, arrival_datetime, departure_datetime, stop_order)
                    VALUES (?,?,?,?,?,?)
                """, (
                    voyage_id,
                    stop["port_name"],
                    stop.get("country"),
                    stop.get("arrival_datetime"),
                    stop.get("departure_datetime"),
                    stop.get("stop_order", 0),
                ))
                stop_count += 1

        conn.commit()
        return ship_id, voyage_count, stop_count
    finally:
        conn.close()


# ── Export: SQLite → itineraries.json ────────────────────────────────────────

def map_port_name(raw: str) -> str:
    """Map CruiseDig port name to WAKE CRUISE_PORTS name."""
    if not raw:
        return raw
    # Try full name
    key = raw.lower().strip()
    if key in PORT_MAP:
        return PORT_MAP[key]
    # Try city part only (before first comma)
    city = raw.split(",")[0].strip().lower()
    if city in PORT_MAP:
        return PORT_MAP[city]
    # Return the city part (cleaner than "City, Country")
    return raw.split(",")[0].strip() if ", " in raw else raw


def export_itineraries() -> tuple[int, int]:
    """
    Query SQLite and write itineraries.json.
    Format: { generated, source, ports: { portName: [{s, d, a, e}] } }
    Returns (port_count, call_count).
    """
    conn = get_db()
    try:
        today = date.today().isoformat()
        future = (date.today() + timedelta(days=90)).isoformat()

        rows = conn.execute("""
            SELECT
                sh.name           AS ship_name,
                ps.port_name      AS raw_port,
                ps.arrival_datetime,
                ps.departure_datetime
            FROM port_stops ps
            JOIN voyages v  ON ps.voyage_id = v.id
            JOIN ships   sh ON v.ship_id    = sh.id
            WHERE (
                  (ps.arrival_datetime   IS NOT NULL AND ps.arrival_datetime   >= ?)
               OR (ps.departure_datetime IS NOT NULL AND ps.departure_datetime >= ?)
            )
              AND (
                  (ps.arrival_datetime   IS NULL OR ps.arrival_datetime   <= ?)
               OR (ps.departure_datetime IS NULL OR ps.departure_datetime <= ?)
            )
            ORDER BY COALESCE(ps.arrival_datetime, ps.departure_datetime)
        """, (today, today, future + " 23:59", future + " 23:59")).fetchall()

        ports: dict[str, list[dict]] = {}
        seen: dict[str, set[str]] = {}

        for row in rows:
            raw_port = row["raw_port"]
            if not raw_port:
                continue
            ship_name = row["ship_name"] or "Unknown"
            arr_raw = row["arrival_datetime"] or ""
            dep_raw = row["departure_datetime"] or ""

            date_str = (arr_raw[:10] if arr_raw else None) or (dep_raw[:10] if dep_raw else None)
            if not date_str:
                continue

            arr_time = arr_raw[11:16] if len(arr_raw) > 10 else ""
            dep_time = dep_raw[11:16] if len(dep_raw) > 10 else ""

            wake_port = map_port_name(raw_port)
            dedup_key = f"{date_str}|{ship_name.lower()}"

            if wake_port not in seen:
                seen[wake_port] = set()
            if dedup_key in seen[wake_port]:
                continue
            seen[wake_port].add(dedup_key)

            ports.setdefault(wake_port, []).append(
                {"s": ship_name, "d": date_str, "a": arr_time, "e": dep_time}
            )

        for calls in ports.values():
            calls.sort(key=lambda c: c["d"])

        out = {
            "generated": int(time.time() * 1000),
            "source": "cruisedig",
            "ports": ports,
        }
        ITIN_JSON_PATH.write_text(json.dumps(out, ensure_ascii=False))
        total = sum(len(v) for v in ports.values())
        logging.info("Exported itineraries.json: %d ports, %d call records", len(ports), total)
        return len(ports), total
    finally:
        conn.close()


# ── Full scrape run ───────────────────────────────────────────────────────────

def needs_refresh() -> bool:
    """True if DB is empty or any ship hasn't been scraped in 24 hours."""
    conn = get_db()
    try:
        total = conn.execute("SELECT COUNT(*) FROM ships").fetchone()[0]
        if total == 0:
            return True
        stale = conn.execute("""
            SELECT COUNT(*) FROM ships
            WHERE last_scraped_at IS NULL
               OR last_scraped_at < datetime('now', '-24 hours')
        """).fetchone()[0]
        return stale > 0
    finally:
        conn.close()


def run_scrape() -> None:
    """Discover → scrape each ship → store in SQLite → export JSON."""
    start_ts = time.time()
    logging.info("=== CruiseDig scrape started ===")

    slugs = discover_ships()
    if not slugs:
        logging.error("No ship slugs discovered — aborting.")
        return

    total_ships = total_voyages = total_stops = 0
    failures: list[str] = []

    for idx, slug in enumerate(slugs, 1):
        logging.info("[%d/%d] %s", idx, len(slugs), slug)
        try:
            data = scrape_ship(slug)
            if data is None:
                logging.warning("  Skipping %s (fetch failed)", slug)
                failures.append(slug)
                polite_sleep()
                continue

            ship_id, vcnt, scnt = upsert_ship(data)
            total_ships += 1
            total_voyages += vcnt
            total_stops += scnt
            logging.info(
                "  %s → %d voyages, %d port stops",
                data.get("name", slug), vcnt, scnt,
            )
        except Exception as exc:
            logging.error("  Error on %s: %s", slug, exc, exc_info=True)
            failures.append(slug)

        polite_sleep()

    port_count, call_count = export_itineraries()

    elapsed = time.time() - start_ts
    logging.info(
        "=== Scrape done %.1fs | ships=%d voyages=%d stops=%d ports=%d calls=%d failures=%d ===",
        elapsed, total_ships, total_voyages, total_stops, port_count, call_count, len(failures),
    )
    if failures:
        logging.warning("Failed (%d): %s", len(failures), ", ".join(failures[:30]))

    sep = "=" * 62
    print(f"\n{sep}")
    print(f"  SCRAPE SUMMARY")
    print(f"  Ships scraped      : {total_ships}")
    print(f"  Voyages collected  : {total_voyages}")
    print(f"  Port stops stored  : {total_stops}")
    print(f"  Ports in JSON      : {port_count}")
    print(f"  Port call records  : {call_count}")
    print(f"  Failures           : {len(failures)}")
    print(f"  Elapsed            : {elapsed:.1f}s")
    print(f"{sep}\n")


# ── Scheduler ─────────────────────────────────────────────────────────────────

def start_scheduler() -> None:
    """Run an immediate scrape if needed, then schedule every 24 hours."""
    if needs_refresh():
        logging.info("DB empty or stale — running initial scrape now.")
        run_scrape()

    scheduler = BlockingScheduler(timezone="UTC")
    next_run = datetime.now(timezone.utc) + timedelta(hours=24)
    scheduler.add_job(run_scrape, "interval", hours=24, id="daily_scrape", next_run_time=next_run)
    logging.info("Scheduler running. Next run at %s UTC.", next_run.strftime("%Y-%m-%d %H:%M"))
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logging.info("Scheduler stopped.")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    setup_logging()
    init_db()

    parser = argparse.ArgumentParser(description="CruiseDig itinerary scraper for WAKE")
    parser.add_argument("--run-now", action="store_true",
                        help="Run a full scrape immediately then exit (used by GitHub Actions)")
    args = parser.parse_args()

    if args.run_now:
        run_scrape()
    else:
        start_scheduler()


if __name__ == "__main__":
    main()
