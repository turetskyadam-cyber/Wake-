#!/usr/bin/env python3
"""Generate WAKE app icons as PNG files using only built-in Python modules."""

import struct, zlib, os, math

# Brand colors
BG   = (4, 14, 20)       # #040e14 — deep ocean
GOLD = (226, 189, 114)   # #e2bd72 — brass/gold
GOLD2= (255, 218, 140)   # highlight
DARK = (2,  8,  12)      # slightly deeper for inner ring

def mk_png(pixels, size):
    """Encode a size×size list of (r,g,b,a) tuples as a PNG binary."""
    def chunk(name, data):
        c = struct.pack('>I', len(data)) + name + data
        return c + struct.pack('>I', zlib.crc32(name + data) & 0xffffffff)

    raw = b''
    for row in pixels:
        raw += b'\x00'  # filter type None
        for r, g, b, a in row:
            raw += bytes([r, g, b, a])

    ihdr = struct.pack('>IIBBBBB', size, size, 8, 2, 0, 0, 0)
    # Use RGBA (color type 6)
    ihdr = struct.pack('>II', size, size) + bytes([8, 6, 0, 0, 0])
    idat = zlib.compress(raw, 9)

    return (
        b'\x89PNG\r\n\x1a\n'
        + chunk(b'IHDR', ihdr)
        + chunk(b'IDAT', idat)
        + chunk(b'IEND', b'')
    )

def lerp_color(c1, c2, t):
    return tuple(int(c1[i] + (c2[i]-c1[i])*t) for i in range(3))

def dist(x, y, cx, cy):
    return math.sqrt((x-cx)**2 + (y-cy)**2)

def render(size):
    cx, cy = size/2, size/2
    R = size/2

    # Corner radius for squircle mask
    corner_r = size * 0.22
    pixels = []

    # Precompute key radii for the design (scaled to size)
    # Design: navy squircle bg + a "wake" ripple arc + stylized W

    # Ripple radii (fraction of half-size)
    ripple_fracs = [0.30, 0.50, 0.70]
    ripple_thick = size * 0.025  # line thickness

    # W shape — defined as normalized coords (-1..1), then scaled
    # W: 5 peaks, each as (nx, ny) in [-1,1] space
    wpts_norm = [
        (-0.60, -0.28),   # TL
        (-0.34,  0.28),   # inner-L dip
        ( 0.00, -0.10),   # center peak
        ( 0.34,  0.28),   # inner-R dip
        ( 0.60, -0.28),   # TR
    ]
    wpts = [(cx + nx*R*0.72, cy + ny*R*0.68) for nx, ny in wpts_norm]
    w_thick = size * 0.075

    def in_squircle(px, py):
        # Rounded square mask (squircle approximation via superellipse p=4)
        nx = (px - cx) / (R - corner_r)
        ny = (py - cy) / (R - corner_r)
        return (abs(nx)**4 + abs(ny)**4) <= 1.0

    def dist_to_segment(px, py, ax, ay, bx, by):
        dx, dy = bx-ax, by-ay
        if dx == 0 and dy == 0:
            return dist(px, py, ax, ay)
        t = max(0, min(1, ((px-ax)*dx + (py-ay)*dy) / (dx*dx + dy*dy)))
        return dist(px, py, ax + t*dx, ay + t*dy)

    def w_dist(px, py):
        """Min distance from (px,py) to the W polyline."""
        mn = 1e9
        for i in range(len(wpts)-1):
            d = dist_to_segment(px, py, wpts[i][0], wpts[i][1], wpts[i+1][0], wpts[i+1][1])
            mn = min(mn, d)
        return mn

    for row in range(size):
        prow = []
        for col in range(size):
            px, py = col + 0.5, row + 0.5

            # Alpha: squircle mask with smooth edge
            sq_nx = (px - cx) / (R - corner_r)
            sq_ny = (py - cy) / (R - corner_r)
            sq_val = abs(sq_nx)**4 + abs(sq_ny)**4
            if sq_val > 1.08:
                prow.append((0, 0, 0, 0))
                continue
            sq_alpha = max(0.0, min(1.0, (1.08 - sq_val) / 0.08))

            # Base background gradient (slightly lighter at center)
            d_from_center = dist(px, py, cx, cy) / R
            bg_t = d_from_center * 0.35
            r0 = int(BG[0] * (1 - bg_t * 0.5))
            g0 = int(BG[1] * (1 - bg_t * 0.4))
            b0 = int(BG[2] * (1 - bg_t * 0.3))
            br, bg, bb = r0, g0, b0

            # Ripple arcs
            ripple_val = 0.0
            for frac in ripple_fracs:
                arc_r = R * frac
                d_arc = abs(dist(px, py, cx, cy) - arc_r)
                # Only draw the arc in the lower 3/4 (wake emanates forward)
                angle = math.atan2(py - cy, px - cx)  # -pi..pi
                # Arc spans from -150° to +150° (bottom-heavy, like a real wake)
                in_arc = not (-math.pi*0.22 < angle < math.pi*0.22)
                if in_arc:
                    v = max(0, 1 - d_arc / ripple_thick) ** 1.4
                    ripple_val = max(ripple_val, v * (0.55 + 0.15 * frac))

            # W stroke
            wd = w_dist(px, py)
            w_val = max(0.0, 1.0 - wd / (w_thick * 0.5))
            w_val = min(1.0, w_val ** 0.7)

            # Composite: bg → ripple → W
            # Ripple layer
            rr = int(br + (GOLD[0] - br) * ripple_val)
            rg = int(bg + (GOLD[1] - bg) * ripple_val)
            rb = int(bb + (GOLD[2] - bb) * ripple_val)

            # W layer (brighter gold on top)
            wr = int(rr + (GOLD2[0] - rr) * w_val)
            wg = int(rg + (GOLD2[1] - rg) * w_val)
            wb = int(rb + (GOLD2[2] - rb) * w_val)

            a = int(sq_alpha * 255)
            prow.append((wr, wg, wb, a))
        pixels.append(prow)
    return pixels

def make_icon(size, path):
    print(f"  Rendering {size}×{size}…", end=" ", flush=True)
    pixels = render(size)
    png = mk_png(pixels, size)
    with open(path, 'wb') as f:
        f.write(png)
    print(f"→ {path} ({len(png)//1024}KB)")

os.makedirs("icons", exist_ok=True)
make_icon(512, "icons/icon-512.png")
make_icon(192, "icons/icon-192.png")
make_icon(180, "icons/apple-touch-icon.png")
make_icon(32,  "icons/favicon-32.png")
print("Done.")
