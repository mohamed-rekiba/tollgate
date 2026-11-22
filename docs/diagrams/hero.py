"""The README banner: an isometric line drawing of a change passing the gate.

On the left, the name and the promise. On the right, on a fine grid: the AI's
room, the gate with its barrier, and the main branch. One
change leaves the room, waits at the gate while the locked tests run, the
barrier lifts only after the tests pass, and it goes in. Before that, a fail sends it
back to the room on the red path.

Drawn by build.py as hero.svg and hero-dark.svg. Plain SVG: real text, no
script, no external file. Motion is CSS and SMIL, and stops under
prefers-reduced-motion.
"""

from itertools import pairwise
from xml.sax.saxutils import escape

W, H = 1200, 600
OX, OY, S = 915, 300, 0.78  # where the ground's origin sits on the page, and its scale
MONO = ("ui-monospace, SFMono-Regular, 'JetBrains Mono', 'Cascadia Mono', Menlo, Consolas, "
        "'Liberation Mono', monospace")

COLORS = {
    "light": {
        "page": "#ffffff", "panel": "#f6f8fa", "ink": "#1f2328", "muted": "#59636e",
        "grid": "#8c959f", "line": "#d1d9e0", "fail": "#cf222e",
        "ai": ("#8250df", "#f6f1ff", "#e6dafc", "#cfbcf6"),
        "gate": ("#9a6700", "#fff6d9", "#fde9ac", "#f3d27a"),
        "main": ("#1a7f37", "#eaf7ee", "#cdeed6", "#a8dcb6"),
    },
    "dark": {
        "page": "#0d1117", "panel": "#151b23", "ink": "#f0f6fc", "muted": "#9198a1",
        "grid": "#3d444d", "line": "#3d444d", "fail": "#f85149",
        "ai": ("#ab7df8", "#2a1f45", "#211836", "#19122a"),
        "gate": ("#d29922", "#3a2c0c", "#2d2209", "#221a06"),
        "main": ("#3fb950", "#12301b", "#0e2615", "#0a1d10"),
    },
}

TITLE = "Tollgate: let AI write your code, merge only what works"
DESC = ("A banner. On the left: Tollgate, a plugin for Claude Code. Let AI write your code, "
        "and merge only what works: tests are written before the code, the AI cannot change "
        "them, and nothing reaches the main branch until they pass. On the right, an isometric "
        "drawing: a change leaves the AI and stops at the gate while the tests run. They fail, "
        "and it goes back to the AI on a red path. It comes again, it scores 70% or more, the barrier "
        "lifts, and it goes into the main branch.")


def iso(x, y, z=0.0):
    return OX + (x - y) * 0.866 * S, OY + ((x + y) * 0.5 - z) * S


def pts(*points):
    return " ".join(f"{px:.1f},{py:.1f}" for px, py in points)


def prism(x0, y0, x1, y1, z0, z1, faces, stroke, width=1.4, opacity=1.0):
    """A box on the ground: top, front-left, and front-right faces."""
    top, left, right = faces
    a = iso(x0, y1, z1)
    b = iso(x1, y1, z1)
    c = iso(x1, y0, z1)
    d = iso(x0, y0, z1)
    b0 = iso(x1, y1, z0)
    a0 = iso(x0, y1, z0)
    c0 = iso(x1, y0, z0)
    o = f' fill-opacity="{opacity}"' if opacity < 1 else ""
    common = f'stroke="{stroke}" stroke-width="{width}" stroke-linejoin="round"{o}'
    return [
        f'<polygon points="{pts(a, b, b0, a0)}" fill="{left}" {common}/>',
        f'<polygon points="{pts(b, c, c0, b0)}" fill="{right}" {common}/>',
        f'<polygon points="{pts(a, b, c, d)}" fill="{top}" {common}/>',
    ]


def label(x, y, z, head, sub, c, anchor="middle"):
    px, py = iso(x, y, z)
    return [
        (f'<text x="{px:.1f}" y="{py:.1f}" text-anchor="{anchor}" font-size="12" font-weight="700" '
        f'letter-spacing="1.6" fill="{c["ink"]}">{escape(head)}</text>'),
        (f'<text x="{px:.1f}" y="{py + 17:.1f}" text-anchor="{anchor}" font-size="12" '
        f'fill="{c["muted"]}">{escape(sub)}</text>'),
    ]


def grid(c):
    out = ['<g mask="url(#fade)" stroke-width="1">']
    for k in range(-330, 331, 30):
        a, b = iso(k, -330), iso(k, 330)
        out.append(f'<line x1="{a[0]:.1f}" y1="{a[1]:.1f}" x2="{b[0]:.1f}" y2="{b[1]:.1f}" '
                   f'stroke="{c["grid"]}" stroke-opacity="0.45"/>')
        a, b = iso(-330, k), iso(330, k)
        out.append(f'<line x1="{a[0]:.1f}" y1="{a[1]:.1f}" x2="{b[0]:.1f}" y2="{b[1]:.1f}" '
                   f'stroke="{c["grid"]}" stroke-opacity="0.45"/>')
    out.append("</g>")
    return out


def room(c):
    stroke, top, left, right = c["ai"]
    out = []
    # A glass room: back walls first, then the builder inside, then the front edges.
    out += prism(-55, 175, 55, 285, 0, 4, (top, left, right), stroke)
    out += prism(-20, 212, 20, 252, 4, 42, (top, left, right), stroke)
    sx, sy = iso(-20, 232, 30)
    ex, ey = iso(-20, 214, 30)
    out.append(f'<line x1="{sx:.1f}" y1="{sy:.1f}" x2="{ex:.1f}" y2="{ey:.1f}" stroke="{stroke}" '
               f'stroke-width="1.4"/>')
    for x, y in ((-55, 175), (55, 175), (55, 285), (-55, 285)):
        a, b = iso(x, y, 4), iso(x, y, 96)
        out.append(f'<line x1="{a[0]:.1f}" y1="{a[1]:.1f}" x2="{b[0]:.1f}" y2="{b[1]:.1f}" '
                   f'stroke="{stroke}" stroke-width="1.2" stroke-dasharray="3 4"/>')
    corners = [iso(-55, 175, 96), iso(55, 175, 96), iso(55, 285, 96), iso(-55, 285, 96)]
    out.append(f'<polygon points="{pts(*corners)}" fill="{top}" fill-opacity="0.35" '
               f'stroke="{stroke}" stroke-width="1.2" stroke-dasharray="3 4"/>')
    out += label(130, 330, -10, "THE AI", "writes the code in its own copy", c)
    return out


def gate(c):
    stroke, top, left, right = c["gate"]
    out = []
    out += prism(110, -22, 154, 22, 0, 70, (top, left, right), stroke)   # the booth, off the road
    out += prism(104, -28, 160, 28, 70, 76, (top, left, right), stroke)  # its roof
    # A lock on the booth's front face.
    lx, ly = iso(154, 0, 34)
    out.append(f'<rect x="{lx - 6:.1f}" y="{ly - 2:.1f}" width="12" height="10" rx="2" '
               f'fill="{stroke}"/>')
    out.append(f'<path d="M{lx - 3.5:.1f},{ly - 2:.1f} v-3.5 a3.5,3.5 0 0 1 7,0 v3.5" '
               f'fill="none" stroke="{stroke}" stroke-width="1.8"/>')
    out += prism(-78, -6, -66, 6, 0, 22, (top, left, right), stroke)     # the far post
    # The barrier arm: from the booth across the path, striped. It lifts when the tests pass.
    # Low, resting on the far post, so it plainly blocks the road.
    px, py = iso(110, 0, 24)
    ex, ey = iso(-72, 0, 24)
    arm = (f'<line x1="{px:.1f}" y1="{py:.1f}" x2="{ex:.1f}" y2="{ey:.1f}" stroke="{stroke}" '
           f'stroke-width="8" stroke-linecap="round"/>'
           f'<line x1="{px:.1f}" y1="{py:.1f}" x2="{ex:.1f}" y2="{ey:.1f}" '
           f'stroke="{c["page"]}" stroke-width="4" stroke-dasharray="9 9"/>')
    tr = trip()
    dur = tr["dur"]
    keys = ";".join(f"{x / dur:.4f}" for x in tr["lift"])
    shut, open_ = f"0 {px:.1f} {py:.1f}", f"60 {px:.1f} {py:.1f}"
    out.append(f'<g class="moving-arm">{arm}<animateTransform attributeName="transform" '
               f'type="rotate" values="{shut};{shut};{open_};{open_};{shut};{shut}" '
               f'keyTimes="0;{keys};1" dur="{dur:.2f}s" repeatCount="indefinite"/></g>')
    out.append(f'<g class="still-arm">{arm}</g>')
    out.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="4.5" fill="{stroke}"/>')
    out += label(205, 0, -10, "THE GATE", "opens at 70%", c, "start")
    return out


def server(c):
    stroke, top, left, right = c["main"]
    out = []
    for n in range(3):
        z0 = n * 30
        out += prism(-48, -268, 48, -172, z0, z0 + 26, (top, left, right), stroke)
        for k in range(3):
            lx, ly = iso(-48 + 14 + k * 9, -172, z0 + 13)
            out.append(f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="2.2" fill="{stroke}"/>')
        a, b = iso(10, -172, z0 + 13), iso(38, -172, z0 + 13)
        out.append(f'<line x1="{a[0]:.1f}" y1="{a[1]:.1f}" x2="{b[0]:.1f}" y2="{b[1]:.1f}" '
                   f'stroke="{stroke}" stroke-width="2" stroke-linecap="round"/>')
    out += label(0, -220, 175, "MAIN BRANCH", "only changes that pass", c)
    return out


# Where the change stops before the barrier, while the locked tests run.
WAIT_Y = 64


def paths(c):
    stroke = c["ai"][0]
    go = [iso(0, 172, 3), iso(0, -168, 3)]
    back = [iso(-12, WAIT_Y, 3), iso(-165, WAIT_Y, 3), iso(-165, 230, 3), iso(-60, 230, 3)]
    out = [
        (f'<polyline class="main" points="{pts(*go)}" fill="none" stroke="{stroke}" '
        f'stroke-linecap="round" stroke-linejoin="round"/>'),
        (f'<polyline class="side" points="{pts(*back)}" fill="none" stroke="{c["fail"]}" '
        f'stroke-linecap="round" stroke-linejoin="round" marker-end="url(#fail)"/>'),
    ]
    mx, my = iso(-165, 150, 3)
    text = "below 70%: try again"
    w = len(text) * 7.2 + 18
    out.append(f'<rect x="{mx - w / 2:.1f}" y="{my - 11:.1f}" width="{w:.1f}" height="22" rx="11" '
               f'fill="{c["page"]}" stroke="{c["fail"]}"/>')
    out.append(f'<text x="{mx:.1f}" y="{my + 4:.1f}" text-anchor="middle" font-size="12" '
               f'fill="{c["fail"]}">{text}</text>')
    return out, go


def callout(c):
    stroke = c["gate"][0]
    gx, gy = iso(0, 8, 46)
    x, y, w = gx - 310, gy - 185, 270
    out = [
        (f'<line x1="{x + w / 2:.1f}" y1="{y + 78:.1f}" x2="{gx - 8:.1f}" y2="{gy - 4:.1f}" '
        f'stroke="{stroke}" stroke-width="1.2" stroke-dasharray="2 4"/>'),
        f'<circle cx="{gx - 8:.1f}" cy="{gy - 4:.1f}" r="3" fill="{stroke}"/>',
        (f'<rect x="{x:.1f}" y="{y:.1f}" width="{w}" height="78" rx="4" fill="{c["page"]}" '
        f'stroke="{stroke}"/>'),
        f'<rect x="{x:.1f}" y="{y:.1f}" width="{w}" height="22" rx="4" fill="{stroke}"/>',
        f'<rect x="{x:.1f}" y="{y + 14:.1f}" width="{w}" height="8" fill="{stroke}"/>',
        (f'<text x="{x + w / 2:.1f}" y="{y + 15:.1f}" text-anchor="middle" font-size="11" '
        f'font-weight="700" letter-spacing="1.4" fill="{c["page"]}">THE GATE · CHANGE 12</text>'),
        (f'<text x="{x + 12:.1f}" y="{y + 42:.1f}" font-size="12" fill="{c["ink"]}">'
        f'runs 14 tests, written first</text>'),
        (f'<text x="{x + 12:.1f}" y="{y + 62:.1f}" font-size="12" fill="{c["muted"]}">'
        f'the AI cannot edit them</text>'),
    ]
    return out


def timeline():
    """The change's trip: (points, color name, seconds to wait at the end) for each leg."""
    room_exit, wait, main = (0, 172), (0, WAIT_Y), (0, -168)
    fail = [(0, WAIT_Y), (-12, WAIT_Y), (-165, WAIT_Y), (-165, 230), (-60, 230)]
    return [([room_exit, wait], "ai", 1.3),          # to the gate; the tests run
            (fail, "fail", 0.5),                     # they fail: back to the room
            ([room_exit, wait], "ai", 1.3),          # again; the tests run
            ([wait, main], "main", 1.2)]             # they pass: the barrier is up


SPEED = 120  # ground units a second


def trip():
    """The change's trip, worked out once: its path on the page, the moments it
    is at each point, the moments its color changes, and when the barrier is up.

    The ticket and the barrier both animate from this, on the same SVG clock, so
    they cannot drift apart, even when a browser pauses an image out of view.
    """
    points, marks, fills, legs = [], [(0.0, 0.0)], [], []
    now, dist = 0.6, 0.0
    marks.append((now, 0.0))
    for ground, color, wait in timeline():
        pts = [iso(x, y, 3) for x, y in ground]
        if points:
            dist += abs(pts[0][0] - points[-1][0]) + abs(pts[0][1] - points[-1][1])
            marks.append((now, dist))  # a jump between legs takes no time
        points += pts
        fills.append((now, color))
        begin = now
        for (x0, y0), (x1, y1) in pairwise(ground):
            a, b = iso(x0, y0, 3), iso(x1, y1, 3)
            dist += abs(b[0] - a[0]) + abs(b[1] - a[1])
            now += (abs(x1 - x0) + abs(y1 - y0)) / SPEED
            marks.append((now, dist))
        legs.append((begin, now))
        now += wait
        marks.append((now, dist))
    dur = now + 0.4
    marks.append((dur, dist))
    # The barrier starts up only after the change has stopped the second time
    # and the tests have run, is fully up before it moves, and comes down after.
    up = legs[2][1] + 0.5
    down = legs[3][1]
    return {"points": points, "marks": marks, "fills": fills, "dur": dur, "total": dist,
            "lift": (up, up + 0.5, down, min(down + 0.5, dur))}


def ticket(c, go):
    """The change: it fails at the gate once and goes back, then passes into main."""
    del go
    colors = {"ai": c["ai"][0], "fail": c["fail"], "main": c["main"][0]}
    tr = trip()
    dur = tr["dur"]
    path = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in tr["points"])
    key_times = ";".join(f"{m[0] / dur:.4f}" for m in tr["marks"])
    key_points = ";".join(f"{m[1] / tr['total']:.4f}" for m in tr["marks"])
    fills = tr["fills"]
    fill = (f'<animate attributeName="fill" values="{";".join(colors[f] for _, f in fills)}" '
            f'keyTimes="0;{";".join(f"{s / dur:.4f}" for s, _ in fills[1:])}" calcMode="discrete" '
            f'dur="{dur:.2f}s" repeatCount="indefinite"/>')
    return [
        '<g class="ticket">',
        f'<circle r="13" fill="{colors["ai"]}" opacity="0.2">{fill}</circle>',
        f'<circle r="6.5" fill="{colors["ai"]}" stroke="{c["page"]}" stroke-width="2">{fill}</circle>',
        (f'<animateMotion path="{path}" keyPoints="{key_points}" keyTimes="{key_times}" '
         f'calcMode="linear" dur="{dur:.2f}s" repeatCount="indefinite"/>'),
        "</g>",
    ]


def left_panel(c):
    out = []
    # The mark, the lifted arm: a striped barrier arm rises from its pivot and draws
    # a check. The locked tests passed, so the gate opens.
    x, y, s = 60, 52, 54
    g, cut = c["gate"][0], c["page"]
    out.append(f'<g transform="translate({x} {y}) scale({s / 100})">'
               f'<path d="M20 55 L40 75 L82 25" fill="none" stroke="{g}" stroke-width="13" '
               f'stroke-linecap="round" stroke-linejoin="round"/>'
               f'<path d="M47 66.7 L82 25" fill="none" stroke="{cut}" stroke-width="13" '
               f'stroke-dasharray="7 9"/>'
               f'<circle cx="40" cy="75" r="9" fill="{g}"/>'
               f'<circle cx="40" cy="75" r="3.2" fill="{cut}"/></g>')
    out.append(f'<text x="132" y="78" font-size="30" font-weight="700" letter-spacing="4" '
               f'fill="{c["ink"]}">TOLLGATE</text>')
    out.append(f'<text x="133" y="100" font-size="12.5" letter-spacing="2.2" '
               f'fill="{c["muted"]}">A PLUGIN FOR CLAUDE CODE</text>')
    for i, line in enumerate(("Let AI write your code.", "Merge only what works.")):
        out.append(f'<text x="60" y="{212 + i * 56}" font-size="36" font-weight="800" '
                   f'letter-spacing="-0.5" fill="{c["ink"]}">{line}</text>')
    for i, line in enumerate(("Tests are written before the code,",
                              "and the AI cannot change them.",
                              "Nothing reaches main until they pass.")):
        out.append(f'<text x="60" y="{340 + i * 27}" font-size="17" '
                   f'fill="{c["muted"]}">{escape(line)}</text>')
    x = 60
    steps = ("YOU ASK", "TESTS LOCKED", "AI BUILDS", "TESTS PASS", "MERGED")
    for i, word in enumerate(steps):
        w = len(word) * 7.6 + 20
        color = c["gate"][0] if word == "TESTS PASS" else c["ink"]
        out.append(f'<rect x="{x}" y="440" width="{w:.0f}" height="28" rx="3" fill="{c["page"]}" '
                   f'stroke="{color if word == "TESTS PASS" else c["line"]}"/>')
        out.append(f'<text x="{x + w / 2:.1f}" y="459" text-anchor="middle" font-size="11.5" '
                   f'font-weight="700" letter-spacing="0.6" fill="{color}">{word}</text>')
        if i < len(steps) - 1:
            out.append(f'<text x="{x + w + 7:.1f}" y="459" text-anchor="middle" font-size="12" '
                       f'fill="{c["muted"]}">›</text>')
        x += w + 14
    out.append(f'<text x="60" y="548" font-size="12" font-weight="700" letter-spacing="1.6" '
               f'fill="{c["muted"]}">FREE SOFTWARE · APACHE 2.0</text>')
    out.append(f'<text x="{W - 60}" y="548" text-anchor="end" font-size="12" letter-spacing="1" '
               f'fill="{c["muted"]}">github.com/tollgate-ai/tollgate</text>')
    return out


MOTION = (
    ".main{stroke-width:3;stroke-dasharray:0 8;animation:flow .8s linear infinite}"
    ".side{stroke-width:1.8;stroke-dasharray:6 6;animation:side 1.6s linear infinite}"
    "@keyframes flow{to{stroke-dashoffset:-8}}"
    "@keyframes side{to{stroke-dashoffset:-12}}"
    ".still-arm{display:none}"
    "@media (prefers-reduced-motion:reduce){.main,.side{animation:none}"
    ".ticket,.moving-arm{display:none}.still-arm{display:inline}}"
)


def draw(theme: str) -> str:
    c = COLORS[theme]
    route, go = paths(c)
    body = (grid(c) + room(c) + route + gate(c) + server(c) + callout(c) + ticket(c, go)
            + left_panel(c))
    head = [
        (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" '
        f'height="{H}" role="img" aria-labelledby="title desc" font-family="{MONO}">'),
        f'<title id="title">{escape(TITLE)}</title>',
        f'<desc id="desc">{escape(DESC)}</desc>',
        ("<defs>"
        f'<radialGradient id="glow" cx="{OX / W:.3f}" cy="{OY / H:.3f}" r="0.42">'
        '<stop offset="0" stop-color="#fff" stop-opacity="1"/>'
        '<stop offset="1" stop-color="#fff" stop-opacity="0"/></radialGradient>'
        f'<mask id="fade"><rect width="{W}" height="{H}" fill="url(#glow)"/></mask>'
        '<marker id="fail" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="9" '
        'markerHeight="9" markerUnits="userSpaceOnUse" orient="auto-start-reverse">'
        f'<path d="M1,1 L9,5 L1,9 L3.2,5 z" fill="{c["fail"]}"/></marker>'
        "</defs>"),
        f"<style>{MOTION}</style>",
        f'<rect width="{W}" height="{H}" fill="{c["page"]}"/>',
        (f'<rect x="20.5" y="20.5" width="{W - 41}" height="{H - 41}" fill="none" '
        f'stroke="{c["line"]}"/>'),
    ]
    return "\n".join(head + body + ["</svg>"]) + "\n"
