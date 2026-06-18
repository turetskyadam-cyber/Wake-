#!/usr/bin/env python3
"""
Scrape deck plan images from cruisedeckplans.com for ships in the WAKE fleet.
Saves deckplans.json to the repo root.

Usage:
    python tools/scrape-deckplans.py              # scrape all ships in SHIP_SLUGS
    python tools/scrape-deckplans.py Wind-Surf    # scrape one ship
"""
import sys, re, json, time, urllib.request
from pathlib import Path

BASE = "https://www.cruisedeckplans.com"
OUT  = Path(__file__).parent.parent / "deckplans.json"

# Map our ship names (from ships.json) → cruisedeckplans.com slug
SHIP_SLUGS = {
    # Windstar
    "Wind Surf":    "Wind-Surf",
    "Wind Spirit":  "Wind-Spirit",
    "Wind Star":    "Wind-Star",
    "Star Breeze":  "Star-Breeze",
    "Star Legend":  "Star-Legend",
    "Star Pride":   "Star-Pride",
    # Royal Caribbean
    "Adventure of the Seas":    "Adventure-of-the-Seas",
    "Allure of the Seas":       "Allure-of-the-Seas",
    "Anthem of the Seas":       "Anthem-of-the-Seas",
    "Brilliance of the Seas":   "Brilliance-of-the-Seas",
    "Enchantment of the Seas":  "Enchantment-of-the-Seas",
    "Explorer of the Seas":     "Explorer-of-the-Seas",
    "Freedom of the Seas":      "Freedom-of-the-Seas",
    "Grandeur of the Seas":     "Grandeur-of-the-Seas",
    "Harmony of the Seas":      "Harmony-of-the-Seas",
    "Icon of the Seas":         "Icon-of-the-Seas",
    "Independence of the Seas": "Independence-of-the-Seas",
    "Jewel of the Seas":        "Jewel-of-the-Seas",
    "Liberty of the Seas":      "Liberty-of-the-Seas",
    "Mariner of the Seas":      "Mariner-of-the-Seas",
    "Navigator of the Seas":    "Navigator-of-the-Seas",
    "Oasis of the Seas":        "Oasis-of-the-Seas",
    "Odyssey of the Seas":      "Odyssey-of-the-Seas",
    "Ovation of the Seas":      "Ovation-of-the-Seas",
    "Quantum of the Seas":      "Quantum-of-the-Seas",
    "Radiance of the Seas":     "Radiance-of-the-Seas",
    "Rhapsody of the Seas":     "Rhapsody-of-the-Seas",
    "Serenade of the Seas":     "Serenade-of-the-Seas",
    "Spectrum of the Seas":     "Spectrum-of-the-Seas",
    "Star of the Seas":         "Star-of-the-Seas",
    "Symphony of the Seas":     "Symphony-of-the-Seas",
    "Utopia of the Seas":       "Utopia-of-the-Seas",
    "Vision of the Seas":       "Vision-of-the-Seas",
    "Voyager of the Seas":      "Voyager-of-the-Seas",
    "Wonder of the Seas":       "Wonder-of-the-Seas",
    # MSC
    "MSC Armonia":       "MSC-Armonia",
    "MSC Bellissima":    "MSC-Bellissima",
    "MSC Divina":        "MSC-Divina",
    "MSC Euribia":       "MSC-Euribia",
    "MSC Fantasia":      "MSC-Fantasia",
    "MSC Grandiosa":     "MSC-Grandiosa",
    "MSC Lirica":        "MSC-Lirica",
    "MSC Magnifica":     "MSC-Magnifica",
    "MSC Meraviglia":    "MSC-Meraviglia",
    "MSC Musica":        "MSC-Musica",
    "MSC Opera":         "MSC-Opera",
    "MSC Orchestra":     "MSC-Orchestra",
    "MSC Poesia":        "MSC-Poesia",
    "MSC Preziosa":      "MSC-Preziosa",
    "MSC Seascape":      "MSC-Seascape",
    "MSC Seashore":      "MSC-Seashore",
    "MSC Seaside":       "MSC-Seaside",
    "MSC Seaview":       "MSC-Seaview",
    "MSC Sinfonia":      "MSC-Sinfonia",
    "MSC Splendida":     "MSC-Splendida",
    "MSC Virtuosa":      "MSC-Virtuosa",
    "MSC World America": "MSC-World-America",
    "MSC World Europa":  "MSC-World-Europa",
    # Princess
    "Caribbean Princess":  "Caribbean-Princess",
    "Coral Princess":      "Coral-Princess",
    "Crown Princess":      "Crown-Princess",
    "Diamond Princess":    "Diamond-Princess",
    "Discovery Princess":  "Discovery-Princess",
    "Emerald Princess":    "Emerald-Princess",
    "Enchanted Princess":  "Enchanted-Princess",
    "Grand Princess":      "Grand-Princess",
    "Island Princess":     "Island-Princess",
    "Majestic Princess":   "Majestic-Princess",
    "Regal Princess":      "Regal-Princess",
    "Royal Princess":      "Royal-Princess",
    "Ruby Princess":       "Ruby-Princess",
    "Sapphire Princess":   "Sapphire-Princess",
    "Sky Princess":        "Sky-Princess",
    "Sun Princess":        "Sun-Princess",
    # Carnival
    "Carnival Breeze":       "Carnival-Breeze",
    "Carnival Celebration":  "Carnival-Celebration",
    "Carnival Conquest":     "Carnival-Conquest",
    "Carnival Dream":        "Carnival-Dream",
    "Carnival Elation":      "Carnival-Elation",
    "Carnival Firenze":      "Carnival-Firenze",
    "Carnival Freedom":      "Carnival-Freedom",
    "Carnival Glory":        "Carnival-Glory",
    "Carnival Horizon":      "Carnival-Horizon",
    "Carnival Jubilee":      "Carnival-Jubilee",
    "Carnival Legend":       "Carnival-Legend",
    "Carnival Liberty":      "Carnival-Liberty",
    "Carnival Magic":        "Carnival-Magic",
    "Carnival Miracle":      "Carnival-Miracle",
    "Carnival Panorama":     "Carnival-Panorama",
    "Carnival Paradise":     "Carnival-Paradise",
    "Carnival Pride":        "Carnival-Pride",
    "Carnival Radiance":     "Carnival-Radiance",
    "Carnival Spirit":       "Carnival-Spirit",
    "Carnival Splendor":     "Carnival-Splendor",
    "Carnival Sunrise":      "Carnival-Sunrise",
    "Carnival Sunshine":     "Carnival-Sunshine",
    "Carnival Valor":        "Carnival-Valor",
    "Carnival Venezia":      "Carnival-Venezia",
    "Carnival Vista":        "Carnival-Vista",
    # Norwegian
    "Norwegian Aqua":      "Norwegian-Aqua",
    "Norwegian Bliss":     "Norwegian-Bliss",
    "Norwegian Breakaway": "Norwegian-Breakaway",
    "Norwegian Dawn":      "Norwegian-Dawn",
    "Norwegian Encore":    "Norwegian-Encore",
    "Norwegian Epic":      "Norwegian-Epic",
    "Norwegian Escape":    "Norwegian-Escape",
    "Norwegian Gem":       "Norwegian-Gem",
    "Norwegian Getaway":   "Norwegian-Getaway",
    "Norwegian Jade":      "Norwegian-Jade",
    "Norwegian Jewel":     "Norwegian-Jewel",
    "Norwegian Joy":       "Norwegian-Joy",
    "Norwegian Pearl":     "Norwegian-Pearl",
    "Norwegian Prima":     "Norwegian-Prima",
    "Norwegian Sky":       "Norwegian-Sky",
    "Norwegian Spirit":    "Norwegian-Spirit",
    "Norwegian Star":      "Norwegian-Star",
    "Norwegian Sun":       "Norwegian-Sun",
    "Norwegian Viva":      "Norwegian-Viva",
    # Norwegian (remaining)
    "Pride of America":    "Pride-of-America",
    # Carnival (remaining)
    "Mardi Gras":          "Mardi-Gras",
    # Celebrity
    "Celebrity Apex":          "Celebrity-Apex",
    "Celebrity Ascent":        "Celebrity-Ascent",
    "Celebrity Beyond":        "Celebrity-Beyond",
    "Celebrity Constellation": "Celebrity-Constellation",
    "Celebrity Eclipse":       "Celebrity-Eclipse",
    "Celebrity Edge":          "Celebrity-Edge",
    "Celebrity Equinox":       "Celebrity-Equinox",
    "Celebrity Infinity":      "Celebrity-Infinity",
    "Celebrity Millennium":    "Celebrity-Millennium",
    "Celebrity Reflection":    "Celebrity-Reflection",
    "Celebrity Silhouette":    "Celebrity-Silhouette",
    "Celebrity Solstice":      "Celebrity-Solstice",
    "Celebrity Summit":        "Celebrity-Summit",
    # Holland America
    "Eurodam":         "Eurodam",
    "Koningsdam":      "Koningsdam",
    "Nieuw Amsterdam": "Nieuw-Amsterdam",
    "Nieuw Statendam": "Nieuw-Statendam",
    "Noordam":         "Noordam",
    "Noorddam":        "Noorddam",
    "Oosterdam":       "Oosterdam",
    "Rotterdam":       "Rotterdam",
    "Volendam":        "Volendam",
    "Westerdam":       "Westerdam",
    "Zaandam":         "Zaandam",
    "Zuiderdam":       "Zuiderdam",
    # Disney
    "Disney Adventure": "Disney-Adventure",
    "Disney Dream":     "Disney-Dream",
    "Disney Fantasy":   "Disney-Fantasy",
    "Disney Magic":     "Disney-Magic",
    "Disney Treasure":  "Disney-Treasure",
    "Disney Wish":      "Disney-Wish",
    "Disney Wonder":    "Disney-Wonder",
    # Costa
    "Costa Deliziosa":   "Costa-Deliziosa",
    "Costa Diadema":     "Costa-Diadema",
    "Costa Fascinosa":   "Costa-Fascinosa",
    "Costa Favolosa":    "Costa-Favolosa",
    "Costa Fortuna":     "Costa-Fortuna",
    "Costa Luminosa":    "Costa-Luminosa",
    "Costa Magica":      "Costa-Magica",
    "Costa Mediterranea":"Costa-Mediterranea",
    "Costa Pacifica":    "Costa-Pacifica",
    "Costa Serena":      "Costa-Serena",
    "Costa Smeralda":    "Costa-Smeralda",
    "Costa Toscana":     "Costa-Toscana",
    # AIDA
    "AIDAbella":  "AIDAbella",
    "AIDAblu":    "AIDAblu",
    "AIDAcosma":  "AIDAcosma",
    "AIDAdiva":   "AIDAdiva",
    "AIDAluna":   "AIDAluna",
    "AIDAmar":    "AIDAmar",
    "AIDAnova":   "AIDAnova",
    "AIDAperla":  "AIDAperla",
    "AIDAprima":  "AIDAprima",
    "AIDAsol":    "AIDAsol",
    "AIDAstella": "AIDAstella",
    # P&O Cruises
    "Arcadia":  "Arcadia",
    "Arvia":    "Arvia",
    "Aurora":   "Aurora",
    "Azura":    "Azura",
    "Britannia":"Britannia",
    "Iona":     "Iona",
    "Ventura":  "Ventura",
    # Cunard
    "Queen Anne":     "Queen-Anne",
    "Queen Elizabeth":"Queen-Elizabeth",
    "Queen Mary 2":   "Queen-Mary-2",
    "Queen Victoria": "Queen-Victoria",
    # Oceania
    "Oceania Insignia": "Insignia",
    "Oceania Marina":   "Oceania-Marina",
    "Oceania Nautica":  "Nautica",
    "Oceania Regatta":  "Regatta",
    "Oceania Riviera":  "Oceania-Riviera",
    "Oceania Sirena":   "Sirena",
    # Regent
    "Seven Seas Explorer": "Seven-Seas-Explorer",
    "Seven Seas Mariner":  "Seven-Seas-Mariner",
    "Seven Seas Navigator":"Seven-Seas-Navigator",
    "Seven Seas Splendor": "Seven-Seas-Splendor",
    "Seven Seas Voyager":  "Seven-Seas-Voyager",
    # Azamara
    "Azamara Journey": "Azamara-Journey",
    "Azamara Onward":  "Azamara-Onward",
    "Azamara Pursuit": "Azamara-Pursuit",
    "Azamara Quest":   "Azamara-Quest",
    # Viking
    "Viking Jupiter":  "Viking-Jupiter",
    "Viking Octantis": "Viking-Octantis",
    "Viking Polaris":  "Viking-Polaris",
    "Viking Sea":      "Viking-Sea",
    "Viking Sky":      "Viking-Sky",
    "Viking Star":     "Viking-Star",
    "Viking Venus":    "Viking-Venus",
    # Virgin Voyages
    "Brilliant Lady": "Brilliant-Lady",
    "Resilient Lady": "Resilient-Lady",
    "Scarlet Lady":   "Scarlet-Lady",
    "Valiant Lady":   "Valiant-Lady",
}

HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}


def fetch(url):
    req = urllib.request.Request(url, headers=HEADERS)
    return urllib.request.urlopen(req, timeout=15).read().decode("utf-8", errors="replace")


def find_nav_html(slug):
    """Try deck numbers 0-12 until one returns a valid page with nav links."""
    for start in range(0, 13):
        try:
            html = fetch(f"{BASE}/ships/deckbydeck.php?ship={slug}&deck={start}")
            # Valid page has the slug in image paths
            if slug in html:
                return html
        except Exception:
            pass
        time.sleep(0.2)
    return ""


def scrape_ship(ship_name, slug):
    print(f"\n  Scraping {ship_name} ({slug})…")

    # First pass: find all deck numbers from the nav
    html0 = find_nav_html(slug)
    if not html0:
        print(f"  Could not load any deck page for {slug}")
        return []

    deck_nums = sorted(set(re.findall(r'deck=(\d+)', html0)), key=int)
    print(f"  Decks found in nav: {deck_nums}")

    decks = []
    for num in deck_nums:
        time.sleep(0.4)
        try:
            html = fetch(f"{BASE}/ships/deckbydeck.php?ship={slug}&deck={num}")
        except Exception as e:
            print(f"    Deck {num}: fetch failed ({e}), skipping")
            continue

        # Deck name from nav link text for this number
        name_match = re.search(
            rf'deck={num}[^>]*>\s*([^<]{{2,40}})</a>', html)
        deck_name = name_match.group(1).strip() if name_match else f"Deck {num}"
        deck_name = re.sub(r'\s+', ' ', deck_name).strip()

        # Prefer webp, fall back to gif
        webp_match = re.search(rf'{slug}/images/([^\s"\'<>]+\.webp)', html)
        gif_match  = re.search(rf'{slug}/images/([^\s"\'<>]+\.gif)', html)
        img_match  = webp_match or gif_match
        if not img_match:
            print(f"    Deck {num} ({deck_name}): no image found, skipping")
            continue

        img_file = img_match.group(1)
        img_url  = f"{BASE}/DP/ships/{slug}/images/{img_file}"

        # Quick HEAD to confirm image is real
        try:
            req = urllib.request.Request(img_url, method="HEAD", headers=HEADERS)
            resp = urllib.request.urlopen(req, timeout=8)
            if resp.status != 200:
                raise ValueError(f"HTTP {resp.status}")
        except Exception as e:
            print(f"    Deck {num} ({deck_name}): image unreachable ({e}), skipping")
            continue

        print(f"    Deck {num}: {deck_name} → {img_file}")
        decks.append({
            "num":  int(num),
            "name": deck_name,
            "url":  img_url,
        })

    return decks


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else None

    # Load existing data to merge
    existing = {}
    if OUT.exists():
        existing = json.loads(OUT.read_text())

    ships_to_run = {k: v for k, v in SHIP_SLUGS.items()
                    if target is None or v == target or k == target}

    if not ships_to_run:
        print(f"No matching ship for '{target}'. Known: {list(SHIP_SLUGS.values())}")
        sys.exit(1)

    for ship_name, slug in ships_to_run.items():
        decks = scrape_ship(ship_name, slug)
        if decks:
            existing[ship_name] = {
                "source": "cruisedeckplans.com",
                "slug":   slug,
                "decks":  decks,
            }
            print(f"  ✓ {ship_name}: {len(decks)} decks")
        else:
            print(f"  ✗ {ship_name}: no decks scraped")

    OUT.write_text(json.dumps(existing, indent=2) + "\n")
    print(f"\nSaved → {OUT}")


if __name__ == "__main__":
    main()
