# WAKE — Live Cruise Fleet Tracker

A single-file, zero-build web app that plots the world's major cruise ships on a
map in real time, using **live AIS broadcasts**. Drill down from cruise line →
ship → a cinematic focus on any vessel.

![status](https://img.shields.io/badge/feed-live%20AIS-5ad6a0)

## What it does

- **Live positions** for ~69 ships across 11 lines (Royal Caribbean, Carnival,
  Norwegian, MSC, Princess, Celebrity, Disney, Virgin Voyages, Holland America,
  Cunard, Costa), streamed over a WebSocket and filtered to a curated, verified
  list of cruise-ship MMSIs.
- **Drill-down navigator:** pick a line to fly the camera to its ships, then a
  ship to zoom in with live latitude/longitude, heading, speed, status and AIS
  destination ("next port").
- **Wake trails**, breathing markers, staggered reveals and reduced-motion
  support.
- **Resilient:** auto-reconnect, tab-hidden pause, last-known positions cached
  to `localStorage` (the map is never blank on reload), and a clearly-labelled
  demo fallback if the feed is unreachable.

## Run it

It's one file. Open `index.html` in a browser, or serve it:

```bash
python3 -m http.server 8000   # then visit http://localhost:8000/
```

Deployed on static hosts (Vercel, GitHub Pages, Netlify) it serves at the root
automatically, since the file is named `index.html`.

Ships appear as their AIS broadcasts arrive (seconds to a couple of minutes).

## Data & API key

Positions come from the free [aisstream.io](https://aisstream.io) global AIS
WebSocket. The key lives in the `CONFIG` block near the top of the `<script>`
in `index.html`:

```js
const CONFIG = { AISSTREAM_KEY: "…", … };
```

Because the app connects directly from the browser, the key is visible in page
source — that's fine for a free hobby key. Get your own (sign in with GitHub at
aisstream.io) and rotate anytime.

> MMSIs can change when a ship reflags; the curated list in `FLEET` is verified
> against public AIS records with IMO cross-checks. If a ship goes quiet, look
> it up by name/IMO and update its MMSI.
