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
# Add more as we expand beyond Wind Surf
SHIP_SLUGS = {
    "Wind Surf": "Wind-Surf",
}

HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}


def fetch(url):
    req = urllib.request.Request(url, headers=HEADERS)
    return urllib.request.urlopen(req, timeout=15).read().decode("utf-8", errors="replace")


def scrape_ship(ship_name, slug):
    print(f"\n  Scraping {ship_name} ({slug})…")

    # First pass: find all deck numbers from any page's nav
    html0 = fetch(f"{BASE}/ships/deckbydeck.php?ship={slug}&deck=1")
    deck_nums = sorted(set(re.findall(r'deck=(\d+)', html0)), key=int)
    print(f"  Decks found in nav: {deck_nums}")

    decks = []
    for num in deck_nums:
        time.sleep(0.4)
        html = fetch(f"{BASE}/ships/deckbydeck.php?ship={slug}&deck={num}")

        # Deck name from nav link text for this number
        name_match = re.search(
            rf'deck={num}[^>]*>\s*([^<]{{2,40}})</a>', html)
        deck_name = name_match.group(1).strip() if name_match else f"Deck {num}"
        # clean up "Deck Zero" → "Deck 0" etc.
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
