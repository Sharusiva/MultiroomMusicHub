"""
Generates the album covers for the demo library as SVG files in media/covers/.

Each cover is an original geometric "record sleeve" built from one idea that
matches the song (a crescent moon for lo-fi, a striped sun for synthwave, a
faceted ball for disco ...). The app samples the cover's colors to tint the
Now Playing screen, so the music, not the interface, supplies the color.

Usage:  python tools/generate_covers.py
"""
import math
import os
import random

OUT = os.path.join(os.path.dirname(__file__), "..", "media", "covers")
S = 600


def svg(body, bg):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {S} {S}" width="{S}" height="{S}">'
            f'<rect width="{S}" height="{S}" fill="{bg}"/>{body}</svg>')


def midnight_lofi(rng):
    bg, moon, haze, line = "#1F2A44", "#EFE3C8", "#2D3B5C", "#EFE3C8"
    stars = "".join(
        f'<circle cx="{rng.uniform(30, 570):.0f}" cy="{rng.uniform(30, 300):.0f}" r="{rng.choice([1.5, 2, 2.5])}" '
        f'fill="{moon}" opacity="{rng.uniform(.35, .8):.2f}"/>' for _ in range(28))
    blinds = "".join(f'<rect x="0" y="{y}" width="600" height="3" fill="{line}" opacity=".18"/>'
                     for y in range(392, 600, 18))
    return svg(
        f'{stars}<defs><mask id="m"><rect width="600" height="600" fill="#fff"/>'
        f'<circle cx="438" cy="186" r="124" fill="#000"/></mask></defs>'
        f'<circle cx="380" cy="228" r="138" fill="{moon}" mask="url(#m)"/>'
        f'<rect y="380" width="600" height="220" fill="{haze}"/>{blinds}', bg)


def neon_drive(rng):
    bg, sun, grid = "#2A1530", "#F2668B", "#F2668B"
    cy, r = 270, 170
    bands = ""
    y, h = cy + 20, 5
    while y < cy + r:
        bands += f'<rect x="100" y="{y:.0f}" width="400" height="{h:.0f}" fill="{bg}"/>'
        y += h + 14
        h += 5
    lines = ""
    horizon = 400
    for i in range(-8, 9):
        lines += f'<line x1="300" y1="{horizon}" x2="{300 + i * 90}" y2="600" stroke="{grid}" stroke-width="2" opacity=".55"/>'
    yy, step = horizon + 8, 6
    while yy < 600:
        lines += f'<line x1="0" y1="{yy:.0f}" x2="600" y2="{yy:.0f}" stroke="{grid}" stroke-width="2" opacity=".55"/>'
        step *= 1.45
        yy += step
    return svg(f'<circle cx="300" cy="{cy}" r="{r}" fill="{sun}"/>{bands}'
               f'<rect y="{horizon}" width="600" height="270" fill="{bg}"/>{lines}', bg)


def glass_garden(rng):
    bg = "#E4EDE6"
    return svg(
        '<g style="mix-blend-mode:multiply">'
        '<circle cx="225" cy="250" r="165" fill="#8CC3AF"/>'
        '<circle cx="375" cy="240" r="140" fill="#CBD98E"/>'
        '<circle cx="305" cy="385" r="125" fill="#4E8F86" opacity=".9"/></g>'
        '<line x1="305" y1="510" x2="305" y2="600" stroke="#2F5D57" stroke-width="4"/>'
        '<line x1="225" y1="415" x2="225" y2="600" stroke="#2F5D57" stroke-width="4"/>'
        '<line x1="375" y1="380" x2="375" y2="600" stroke="#2F5D57" stroke-width="4"/>', bg)


def sunday_kitchen(rng):
    bg, red, cloth = "#F3C64A", "#D9442B", "#FBF6EA"
    check = ""
    size = 50
    for row, y in enumerate(range(400, 600, size)):
        for col, x in enumerate(range(0, 600, size)):
            fill = red if (row + col) % 2 == 0 else cloth
            check += f'<rect x="{x}" y="{y}" width="{size}" height="{size}" fill="{fill}"/>'
    return svg(
        f'{check}<ellipse cx="300" cy="350" rx="190" ry="120" fill="{cloth}" stroke="#2B2620" stroke-width="5"/>'
        f'<ellipse cx="300" cy="350" rx="140" ry="84" fill="none" stroke="#2B2620" stroke-width="2" opacity=".35"/>'
        f'<path d="M230 330 C 240 280, 340 270, 370 310 C 400 350, 360 395, 300 390 C 240 388, 220 365, 230 330 Z" fill="#FFFFFF"/>'
        f'<circle cx="305" cy="335" r="36" fill="#F29F05"/>', bg)


def pixel_quest(rng):
    bg, hill, snow, sun = "#1E5B3A", "#A8D86E", "#F1F0D8", "#F1F0D8"
    p = 40
    body = f'<rect x="440" y="80" width="{p * 2}" height="{p * 2}" fill="{sun}"/>'
    h = 5
    for col in range(15):
        h = max(2, min(9, h + rng.choice([-1, 0, 1, 1])))
        for row in range(h):
            y = 600 - (row + 1) * p
            fill = snow if row == h - 1 and h >= 7 else hill
            body += f'<rect x="{col * p}" y="{y}" width="{p}" height="{p}" fill="{fill}"/>'
    body += "".join(f'<rect x="{x}" y="{y}" width="{p}" height="{p}" fill="{bg}" opacity=".35"/>'
                    for x, y in ((80, 520), (240, 480), (400, 520), (520, 440)))
    return svg(body, bg)


def deep_room(rng):
    bg, blue, light = "#0F1720", "#3D7BBE", "#E7EEF6"
    body = ""
    for i, s in enumerate(range(520, 60, -60)):
        off = i * 6
        x = 300 - s / 2 + off * 0.5
        y = 300 - s / 2 - off * 0.3
        body += f'<rect x="{x:.0f}" y="{y:.0f}" width="{s}" height="{s}" fill="none" stroke="{blue}" stroke-width="8" opacity="{1 - i * 0.07:.2f}"/>'
    body += f'<rect x="308" y="262" width="40" height="40" fill="{light}"/>'
    return svg(body, bg)


def rainy_window(rng):
    bg, rain, warm = "#2E4756", "#A9C7D3", "#E8C26A"
    body = f'<rect x="372" y="372" width="120" height="150" fill="{warm}"/>' \
           f'<line x1="432" y1="372" x2="432" y2="522" stroke="{bg}" stroke-width="6"/>' \
           f'<line x1="372" y1="447" x2="492" y2="447" stroke="{bg}" stroke-width="6"/>'
    for _ in range(120):
        x = rng.uniform(0, 600)
        y = rng.uniform(-40, 600)
        ln = rng.uniform(24, 70)
        body += (f'<line x1="{x:.0f}" y1="{y:.0f}" x2="{x - ln * .18:.0f}" y2="{y + ln:.0f}" stroke="{rain}" '
                 f'stroke-width="{rng.choice([2, 2, 3])}" stroke-linecap="round" opacity="{rng.uniform(.25, .75):.2f}"/>')
    return svg(body, bg)


def paper_lanterns(rng):
    bg, ink = "#F2E8D8", "#3B3328"
    body = ""
    for x, y, rx, ry, fill in ((170, 260, 78, 104, "#E0662F"), (330, 370, 92, 120, "#EFA340"), (470, 220, 64, 86, "#E0662F")):
        body += f'<line x1="{x}" y1="0" x2="{x}" y2="{y - ry - 14}" stroke="{ink}" stroke-width="2"/>'
        body += f'<rect x="{x - rx * .45:.0f}" y="{y - ry - 16}" width="{rx * .9:.0f}" height="16" fill="{ink}"/>'
        body += f'<ellipse cx="{x}" cy="{y}" rx="{rx}" ry="{ry}" fill="{fill}"/>'
        for k in (0.35, 0.7):
            body += f'<ellipse cx="{x}" cy="{y}" rx="{rx * k:.0f}" ry="{ry}" fill="none" stroke="{ink}" stroke-width="1.5" opacity=".35"/>'
        body += f'<rect x="{x - rx * .45:.0f}" y="{y + ry}" width="{rx * .9:.0f}" height="12" fill="{ink}"/>'
        body += f'<line x1="{x}" y1="{y + ry + 12}" x2="{x}" y2="{y + ry + 44}" stroke="{ink}" stroke-width="2"/>'
    return svg(body, bg)


def mirrorball(rng):
    bg = "#B3122E"
    tones = ["#F4D6DB", "#E6A9B4", "#FFFFFF", "#D98896", "#F7E6E9", "#C9707F"]
    tiles = ""
    step = 34
    for y in range(110, 490, step):
        for x in range(110, 490, step):
            tiles += f'<rect x="{x}" y="{y}" width="{step - 4}" height="{step - 4}" fill="{rng.choice(tones)}"/>'
    rays = "".join(
        f'<line x1="300" y1="300" x2="{300 + 420 * math.cos(a):.0f}" y2="{300 + 420 * math.sin(a):.0f}" '
        f'stroke="#F4D6DB" stroke-width="3" opacity=".22"/>'
        for a in (i * math.pi / 8 + 0.2 for i in range(16)))
    return svg(f'{rays}<clipPath id="ball"><circle cx="300" cy="300" r="190"/></clipPath>'
               f'<circle cx="300" cy="300" r="194" fill="#7E0C20"/>'
               f'<g clip-path="url(#ball)">{tiles}</g>'
               f'<line x1="300" y1="0" x2="300" y2="106" stroke="#2A0A10" stroke-width="4"/>', bg)


def night_circuit(rng):
    bg, lime = "#171B16", "#B6E33B"
    body = ""
    for _ in range(14):
        x, y = rng.choice(range(0, 601, 50)), rng.choice(range(0, 601, 50))
        pts = [(x, y)]
        for _ in range(rng.randint(2, 4)):
            dx = rng.choice([-1, 0, 1]) * 50 * rng.randint(1, 3)
            dy = rng.choice([-1, 1]) * 50 * rng.randint(1, 3)
            if dx and abs(dx) != abs(dy):
                dx = math.copysign(abs(dy), dx)
            x, y = max(0, min(600, x + dx)), max(0, min(600, y + dy))
            pts.append((x, y))
        path = " ".join(f"{px},{py}" for px, py in pts)
        body += f'<polyline points="{path}" fill="none" stroke="{lime}" stroke-width="6" stroke-linejoin="round" opacity="{rng.uniform(.45, 1):.2f}"/>'
        ex, ey = pts[-1]
        body += f'<circle cx="{ex}" cy="{ey}" r="11" fill="{bg}" stroke="{lime}" stroke-width="5"/>'
    return svg(body, bg)


COVERS = {
    "midnight-lofi": midnight_lofi, "neon-drive": neon_drive, "glass-garden": glass_garden,
    "sunday-kitchen": sunday_kitchen, "pixel-quest": pixel_quest, "deep-room-4am": deep_room,
    "rainy-window": rainy_window, "paper-lanterns": paper_lanterns, "mirrorball": mirrorball,
    "night-circuit": night_circuit,
}


def main():
    os.makedirs(OUT, exist_ok=True)
    for i, (slug, fn) in enumerate(COVERS.items()):
        with open(os.path.join(OUT, f"{slug}.svg"), "w") as f:
            f.write(fn(random.Random(i + 11)))
        print(f"covers/{slug}.svg")


if __name__ == "__main__":
    main()
